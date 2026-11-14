import re
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.config import AppConfig
from zendilohub.core.domain.jobs import JobQueue
from zendilohub.core.http.access import CurrentMember, CurrentPerson, Member, OptionalUser, Public, member_with
from zendilohub.core.http.audit import Unaudited, audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.accounts import CreateAccount, DeleteAccount, TestAccount, UpdateAccount
from ...application.commands.inbound import FETCH_TASK, DeleteFailedEmail, RetryFailedEmail
from ...application.commands.oauth import FinishConnect, MailProviders, StartConnect
from ...application.commands.outbound import ResendReply
from ...application.commands.settings import (
    DeleteFilter,
    DeleteTemplate,
    FilterFields,
    ReorderFilters,
    SaveFilter,
    SaveTemplate,
    SetPersonal,
    SetQueueChannel,
)
from ...application.queries.channels import (
    GetPersonal,
    ListAccounts,
    ListFailedEmails,
    ListFilters,
    ListQueueChannels,
    ListTemplates,
    ReplyDraft,
    TicketDeliveries,
)
from ...application.services.writer import Context
from ...domain.exceptions import OAuthFailedError
from ...domain.models.account import AccountSettings, Passwords, Server
from ...domain.models.mail_filter import Condition, FilterActions
from ...domain.models.templates import QueueChannel
from .schemas import (
    AccountRequest,
    AccountResponse,
    ConnectStartRequest,
    ConnectStartResponse,
    DeliveryResponse,
    DraftResponse,
    FailedEmailResponse,
    FilterOrderRequest,
    FilterRequest,
    FilterResponse,
    MailProvidersResponse,
    PersonalRequest,
    PersonalResponse,
    ProbeResponse,
    QueueChannelRequest,
    QueueChannelResponse,
    RetryResponse,
    ServerRequest,
    TemplateRequest,
    TemplateResponse,
    TemplatesResponse,
)

Admin = Annotated[Member, member_with('channels.manage', people_only=True)]

CALLBACK_PATH = '/email-oauth/callback'
_TENANT = re.compile(r'^[0-9a-f-]{36}$')
_REASON = re.compile(r'[^a-z0-9_]')


def redirect_uri(config: AppConfig, request: Request) -> str:
    """Where the providers send the browser back; register exactly this address with them."""
    base = config.public_url or str(request.base_url).rstrip('/')
    return f'{base}/api/v1{CALLBACK_PATH}'


def _settings(body: AccountRequest) -> tuple[AccountSettings, Passwords]:
    def server(request: ServerRequest) -> Server:
        return Server(host=request.host, port=request.port, security=request.security, username=request.username)

    settings = AccountSettings(
        name=body.name,
        address=body.address,
        display_name=body.display_name,
        queue_id=body.queue_id,
        imap=server(body.imap),
        smtp=server(body.smtp),
        folder=body.folder,
        active=body.active,
    )
    return settings, Passwords(imap=body.imap.password, smtp=body.smtp.password)


def _filter_fields(body: FilterRequest) -> FilterFields:
    actions = body.actions
    return FilterFields(
        name=body.name,
        active=body.active,
        match=body.match,
        conditions=tuple(Condition(**each.model_dump()) for each in body.conditions),
        actions=FilterActions(
            queue_id=actions.queue_id, priority=actions.priority, tags=tuple(actions.tags), ignore=actions.ignore
        ),
        stop=body.stop,
    )


def oauth_callback_routes(bus: CommandBus, config: AppConfig) -> APIRouter:
    """The providers' way back: outside the organization's paths, since its address is registered with them."""
    router = APIRouter(tags=['channels'], dependencies=[Public])

    @router.get(CALLBACK_PATH, response_class=RedirectResponse, dependencies=[audited('email_account.connected')])
    async def callback(
        request: Request,
        principal: OptionalUser,
        state: Annotated[str, Query(max_length=200)] = '',
        code: Annotated[str | None, Query(max_length=4096)] = None,
        error: Annotated[str | None, Query(max_length=200)] = None,
    ) -> RedirectResponse:
        """Finishes connecting a mailbox and goes back to the e-mail account settings."""
        tenant_id = state.split('.', 1)[0]
        page = f'/t/{tenant_id}/email-accounts' if _TENANT.match(tenant_id) else '/'
        try:
            connected = await bus.execute(
                FinishConnect(
                    state=state,
                    code=code,
                    error=error,
                    user_id=principal.user_id if principal else None,
                    redirect_uri=redirect_uri(config, request),
                )
            )
        except OAuthFailedError as failure:
            reason = _REASON.sub('_', failure.reason.lower())[:40] or 'failed'
            return RedirectResponse(f'{page}?{urlencode({"oauth_error": reason})}', status_code=303)
        note_audit(
            request,
            tenant_id=connected.tenant_id,
            target=connected.account.address,
            actor_id=principal.user_id if principal else None,
        )
        query = urlencode({'connected': connected.account.id})
        return RedirectResponse(f'/t/{connected.tenant_id}/email-accounts?{query}', status_code=303)

    return router


def channel_routes(bus: CommandBus, jobs: JobQueue, config: AppConfig) -> APIRouter:
    """E-mail: accounts, signatures and salutations, queue settings, filters, failed mails and what was sent."""
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['channels'])

    async def account_view(tenant_id: str, account_id: str) -> AccountResponse:
        views = await bus.query(ListAccounts(tenant_id, account_id))
        return AccountResponse.of(views[0])

    @router.get('/email-accounts')
    async def accounts(member: Admin) -> list[AccountResponse]:
        return [AccountResponse.of(each) for each in await bus.query(ListAccounts(member.tenant_id))]

    @router.post('/email-accounts', status_code=201, dependencies=[audited('email_account.created')])
    async def create_account(body: AccountRequest, request: Request, member: Admin) -> AccountResponse:
        """A mailbox (IMAP to fetch, SMTP to send); its passwords are stored encrypted and never shown again."""
        settings, passwords = _settings(body)
        account = await bus.execute(CreateAccount(tenant_id=member.tenant_id, settings=settings, passwords=passwords))
        note_audit(request, target=account.address)
        return await account_view(member.tenant_id, account.id)

    @router.patch('/email-accounts/{account_id}', dependencies=[audited('email_account.updated')])
    async def update_account(account_id: Id, body: AccountRequest, request: Request, member: Admin) -> AccountResponse:
        settings, passwords = _settings(body)
        account = await bus.execute(
            UpdateAccount(tenant_id=member.tenant_id, account_id=account_id, settings=settings, passwords=passwords)
        )
        note_audit(request, target=account.address)
        return await account_view(member.tenant_id, account.id)

    @router.delete(
        '/email-accounts/{account_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('email_account.deleted')],
    )
    async def delete_account(account_id: Id, request: Request, member: Admin) -> None:
        account = await bus.execute(DeleteAccount(tenant_id=member.tenant_id, account_id=account_id))
        note_audit(request, target=account.address)

    @router.get('/email-accounts/oauth-providers')
    async def mail_providers(_member: Admin) -> MailProvidersResponse:
        return MailProvidersResponse(providers=list(await bus.query(MailProviders())))

    @router.post('/email-accounts/oauth', dependencies=[audited('email_account.connect_started')])
    async def start_connect(body: ConnectStartRequest, request: Request, member: Admin) -> ConnectStartResponse:
        """
        Connects a mailbox with OAuth (Google, Microsoft 365): a new account in `queue_id`, or `account_id` again.
        The browser then goes to the returned address; the provider sends it back to the settings.
        """
        url = await bus.execute(
            StartConnect(
                tenant_id=member.tenant_id,
                user_id=member.user_id,
                provider=body.provider,
                redirect_uri=redirect_uri(config, request),
                account_id=body.account_id,
                queue_id=body.queue_id,
                name=body.name,
                display_name=body.display_name,
            )
        )
        note_audit(request, target=body.account_id or body.provider)
        return ConnectStartResponse(url=url)

    @router.post('/email-accounts/{account_id}/test', dependencies=[Unaudited])
    async def test_account(account_id: Id, member: Admin) -> ProbeResponse:
        """Logs in to the IMAP and the SMTP server with the stored settings."""
        result = await bus.execute(TestAccount(tenant_id=member.tenant_id, account_id=account_id))
        return ProbeResponse(imap=result.imap, smtp=result.smtp)

    @router.post(
        '/email-accounts/{account_id}/fetch', status_code=202, response_class=Response, dependencies=[Unaudited]
    )
    async def fetch_now(account_id: Id, member: Admin) -> None:
        """Fetches new mail now instead of within the next minute."""
        await account_view(member.tenant_id, account_id)
        await jobs.enqueue(FETCH_TASK, member.tenant_id, account_id)

    @router.get('/text-templates')
    async def templates(member: Admin) -> TemplatesResponse:
        """Signatures and salutations with the placeholders they may use."""
        return TemplatesResponse.of(list(await bus.query(ListTemplates(member.tenant_id))))

    @router.post('/text-templates', status_code=201, dependencies=[audited('text_template.created')])
    async def create_template(body: TemplateRequest, request: Request, member: Admin) -> TemplateResponse:
        template = await bus.execute(
            SaveTemplate(tenant_id=member.tenant_id, kind=body.kind, name=body.name, body=body.body)
        )
        note_audit(request, target=template.name)
        return TemplateResponse.of(template)

    @router.patch('/text-templates/{template_id}', dependencies=[audited('text_template.updated')])
    async def update_template(
        template_id: Id, body: TemplateRequest, request: Request, member: Admin
    ) -> TemplateResponse:
        template = await bus.execute(
            SaveTemplate(
                tenant_id=member.tenant_id, kind=body.kind, name=body.name, body=body.body, template_id=template_id
            )
        )
        note_audit(request, target=template.name)
        return TemplateResponse.of(template)

    @router.delete(
        '/text-templates/{template_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('text_template.deleted')],
    )
    async def delete_template(template_id: Id, request: Request, member: Admin) -> None:
        template = await bus.execute(DeleteTemplate(tenant_id=member.tenant_id, template_id=template_id))
        note_audit(request, target=template.name)

    @router.get('/queue-channels')
    async def queue_channels(member: Admin) -> list[QueueChannelResponse]:
        """How each queue writes (queues without settings are left out)."""
        return [QueueChannelResponse.of(each) for each in await bus.query(ListQueueChannels(member.tenant_id))]

    @router.put('/queue-channels/{queue_id}', dependencies=[audited('queue_channel.changed')])
    async def set_queue_channel(
        queue_id: Id, body: QueueChannelRequest, request: Request, member: Admin
    ) -> QueueChannelResponse:
        settings = await bus.execute(
            SetQueueChannel(QueueChannel(tenant_id=member.tenant_id, queue_id=queue_id, **body.model_dump()))
        )
        note_audit(request, target=queue_id)
        return QueueChannelResponse.of(settings)

    @router.get('/me/email-settings')
    async def personal(member: CurrentPerson) -> PersonalResponse:
        """The caller's name, title and personal signature lines for this organization."""
        return PersonalResponse.of(await bus.query(GetPersonal(member.tenant_id, member.user_id)))

    @router.put('/me/email-settings', dependencies=[Unaudited])
    async def set_personal(body: PersonalRequest, member: CurrentPerson) -> PersonalResponse:
        settings = await bus.execute(
            SetPersonal(
                tenant_id=member.tenant_id,
                user_id=member.user_id,
                name=body.name,
                title=body.title,
                signature=body.signature,
            )
        )
        return PersonalResponse.of(settings)

    @router.get('/mail-filters')
    async def filters(member: Admin) -> list[FilterResponse]:
        """In the order they run."""
        return [FilterResponse.of(each) for each in await bus.query(ListFilters(member.tenant_id))]

    @router.post('/mail-filters', status_code=201, dependencies=[audited('mail_filter.created')])
    async def create_filter(body: FilterRequest, request: Request, member: Admin) -> FilterResponse:
        saved = await bus.execute(SaveFilter(tenant_id=member.tenant_id, fields=_filter_fields(body)))
        note_audit(request, target=saved.name)
        return FilterResponse.of(saved)

    @router.patch('/mail-filters/{filter_id}', dependencies=[audited('mail_filter.updated')])
    async def update_filter(filter_id: Id, body: FilterRequest, request: Request, member: Admin) -> FilterResponse:
        saved = await bus.execute(
            SaveFilter(tenant_id=member.tenant_id, fields=_filter_fields(body), filter_id=filter_id)
        )
        note_audit(request, target=saved.name)
        return FilterResponse.of(saved)

    @router.delete(
        '/mail-filters/{filter_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('mail_filter.deleted')],
    )
    async def delete_filter(filter_id: Id, request: Request, member: Admin) -> None:
        deleted = await bus.execute(DeleteFilter(tenant_id=member.tenant_id, filter_id=filter_id))
        note_audit(request, target=deleted.name)

    @router.put('/mail-filters-order', dependencies=[audited('mail_filter.reordered')])
    async def reorder_filters(body: FilterOrderRequest, member: Admin) -> list[FilterResponse]:
        await bus.execute(ReorderFilters(tenant_id=member.tenant_id, filter_ids=tuple(body.filter_ids)))
        return [FilterResponse.of(each) for each in await bus.query(ListFilters(member.tenant_id))]

    @router.get('/failed-emails')
    async def failed_emails(member: Admin) -> list[FailedEmailResponse]:
        """Received e-mails that could not become tickets, newest first."""
        return [FailedEmailResponse.of(each) for each in await bus.query(ListFailedEmails(member.tenant_id))]

    @router.post('/failed-emails/{failed_id}/retry', dependencies=[audited('failed_email.retried')])
    async def retry_failed(failed_id: Id, member: Admin) -> RetryResponse:
        """Processes the e-mail again (e.g. after fixing a filter); if it fails again, it is listed again."""
        outcome = await bus.execute(RetryFailedEmail(tenant_id=member.tenant_id, failed_id=failed_id))
        return RetryResponse(outcome=outcome)

    @router.delete(
        '/failed-emails/{failed_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('failed_email.deleted')],
    )
    async def delete_failed(failed_id: Id, member: Admin) -> None:
        await bus.execute(DeleteFailedEmail(tenant_id=member.tenant_id, failed_id=failed_id))

    @router.get('/tickets/{ticket_id}/deliveries')
    async def deliveries(ticket_id: Id, member: CurrentMember) -> list[DeliveryResponse]:
        """Whether the replies in a ticket went out by e-mail."""
        return [DeliveryResponse.of(each) for each in await bus.query(TicketDeliveries(member.tenant_id, ticket_id))]

    @router.post(
        '/tickets/{ticket_id}/deliveries/{message_id}/resend',
        status_code=202,
        response_class=Response,
        dependencies=[Unaudited],
    )
    async def resend(ticket_id: Id, message_id: Id, member: CurrentMember) -> None:
        await bus.execute(ResendReply(tenant_id=member.tenant_id, message_id=message_id))

    @router.get('/queues/{queue_id}/reply-draft')
    async def reply_draft(
        queue_id: Id,
        member: CurrentMember,
        number: int | None = None,
        subject: Annotated[str, Query(max_length=250)] = '',
        customer_name: Annotated[str, Query(max_length=200)] = '',
        customer_email: Annotated[str, Query(max_length=254)] = '',
    ) -> DraftResponse:
        """The queue's salutation and signature with the caller's details, to start a reply with."""
        text = await bus.query(
            ReplyDraft(
                Context(
                    tenant_id=member.tenant_id,
                    queue_id=queue_id,
                    user_id=member.user_id,
                    ticket_number=number,
                    ticket_subject=subject,
                    customer_name=customer_name,
                    customer_email=customer_email,
                )
            )
        )
        return DraftResponse(text=text)

    return router
