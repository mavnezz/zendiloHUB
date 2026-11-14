import logging
from dataclasses import dataclass
from typing import Literal

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.files import FileData
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.inbox import InboundEmail
from zendilohub.core.domain.jobs import JobQueue
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

from ...domain.exceptions import AccountNotFoundError, FailedEmailNotFoundError
from ...domain.models.account import EmailAccount
from ...domain.models.email import DEFAULT_PREFIX, ParsedEmail, parse_email, tagged
from ...domain.models.mail_filter import route
from ...domain.models.records import FailedEmail
from ...domain.ports.repositories import (
    AccountRepository,
    FailedEmailRepository,
    FilterRepository,
    QueueChannelRepository,
    TicketMailboxRepository,
)
from ...domain.ports.services import HtmlCleaner, Mailbox, MailboxError, Outbox, OutgoingMail, Tickets
from ..services.writer import Context, Writer
from .accounts import Vault

logger = logging.getLogger(__name__)

FETCH_TASK = 'channels.fetch'
FETCH_LIMIT = 200
"""Mails per account and run; the rest come next time."""
AUTO_REPLIES = RateLimit('channels-auto-reply', limit=3, window_seconds=60 * 60)
"""Auto replies per sender and hour: two robots never write each other forever."""

type Outcome = Literal['created', 'appended', 'ignored', 'duplicate', 'own', 'failed']


@dataclass(frozen=True)
class FetchDue(Command[int]):
    """Hands every active account to the workers to fetch (a scheduled job); returns how many."""


class FetchDueHandler:
    def __init__(self, accounts: AccountRepository, jobs: JobQueue) -> None:
        self._accounts = accounts
        self._jobs = jobs

    async def handle(self, command: FetchDue) -> int:
        accounts = await self._accounts.active()
        for account in accounts:
            await self._jobs.enqueue(FETCH_TASK, account.tenant_id, account.id)
        return len(accounts)


@dataclass(frozen=True)
class FetchAccount(Command[list[Outcome]]):
    tenant_id: str
    account_id: str


class FetchAccountHandler:
    def __init__(
        self, accounts: AccountRepository, vault: Vault, mailbox: Mailbox, process: ProcessEmailHandler, clock: Clock
    ) -> None:
        self._accounts = accounts
        self._vault = vault
        self._mailbox = mailbox
        self._process = process
        self._clock = clock

    async def handle(self, command: FetchAccount) -> list[Outcome]:
        account = await self._accounts.find(command.tenant_id, command.account_id)
        if account is None or not account.active:
            return []
        try:
            fetched = await self._mailbox.fetch(
                account,
                await self._vault.credential(account, 'imap'),
                after_uid=account.last_uid if account.uid_validity else 0,
                uid_validity=account.uid_validity,
                limit=FETCH_LIMIT,
            )
        except MailboxError as error:
            account.failed(str(error) or 'failed', self._clock.now())
            await self._accounts.save(account)
            return []
        outcomes: list[Outcome] = []
        last_uid = account.last_uid if account.uid_validity == fetched.uid_validity else 0
        for uid, raw in fetched.messages:
            outcomes.append(await self._process.handle(ProcessEmail(account.tenant_id, account.id, raw)))
            last_uid = max(last_uid, uid)
        account.fetched(uid_validity=fetched.uid_validity, last_uid=last_uid, now=self._clock.now())
        await self._accounts.save(account)
        return outcomes


@dataclass(frozen=True)
class ProcessEmail(Command[Outcome]):
    """One received e-mail: filters, then its ticket (or a new one), then the queue's auto reply."""

    tenant_id: str
    account_id: str | None
    raw: bytes


class ProcessEmailHandler:
    def __init__(
        self,
        accounts: AccountRepository,
        filters: FilterRepository,
        failed: FailedEmailRepository,
        mailboxes: TicketMailboxRepository,
        queues: QueueChannelRepository,
        tickets: Tickets,
        cleaner: HtmlCleaner,
        auto: AutoReplier,
        ids: IdGenerator,
        clock: Clock,
        max_file_bytes: int,
    ) -> None:
        self._max_file_bytes = max_file_bytes
        self._accounts = accounts
        self._filters = filters
        self._failed = failed
        self._mailboxes = mailboxes
        self._queues = queues
        self._tickets = tickets
        self._cleaner = cleaner
        self._auto = auto
        self._ids = ids
        self._clock = clock

    async def handle(self, command: ProcessEmail) -> Outcome:
        try:
            return await self._process(command)
        except Exception as error:
            logger.exception('An e-mail could not be processed', extra={'tenant': command.tenant_id})
            await self._failed.add(
                FailedEmail(
                    id=self._ids.new_id(),
                    tenant_id=command.tenant_id,
                    account_id=command.account_id,
                    raw=command.raw,
                    error=f'{type(error).__name__}: {error}'[:500],
                    received_at=self._clock.now(),
                )
            )
            return 'failed'

    async def _process(self, command: ProcessEmail) -> Outcome:
        account = await self._accounts.find(command.tenant_id, command.account_id) if command.account_id else None
        if command.account_id and account is None:
            raise AccountNotFoundError()
        mail = parse_email(command.raw)
        if not mail.from_address:
            raise ValueError('The e-mail has no sender')
        if mail.from_address in await self._accounts.addresses(command.tenant_id):
            # Our own mail came back (a copy to ourselves): never a ticket.
            return 'own'
        if mail.message_id and await self._tickets.thread(command.tenant_id, [mail.message_id], None):
            return 'duplicate'
        routing = route(list(await self._filters.of_tenant(command.tenant_id)), mail, command.account_id)
        if routing.ignore:
            return 'ignored'
        prefix = await self._tickets.subject_prefix(command.tenant_id)
        ticket_id = await self._tickets.thread(command.tenant_id, mail.thread_ids, mail.number_tagged(prefix))
        queue_id = routing.queue_id or (account.queue_id if account else None)
        if queue_id is None:
            raise ValueError('No queue for the e-mail')
        received = await self._tickets.receive(
            InboundEmail(
                tenant_id=command.tenant_id,
                queue_id=queue_id,
                ticket_id=ticket_id,
                from_address=mail.from_address,
                from_name=mail.from_name,
                subject=mail.subject,
                body=mail.text,
                body_html=self._cleaner.clean(mail.html) if mail.html else None,
                email_message_id=mail.message_id,
                in_reply_to=mail.in_reply_to,
                references=mail.references,
                to_addresses=mail.to,
                cc_addresses=mail.cc,
                priority=routing.priority,
                tags=routing.tags,
                # Larger files stay in the mailbox: the upload limit holds for e-mails too.
                attachments=tuple(
                    FileData(
                        filename=each.filename,
                        content_type=each.content_type,
                        content=each.content,
                        content_id=each.content_id,
                    )
                    for each in mail.files
                    if len(each.content) <= self._max_file_bytes
                ),
            )
        )
        if account is not None:
            # Replies of a queue without its own sending account go out by the mailbox the customer wrote to.
            await self._mailboxes.remember(command.tenant_id, received.ticket_id, account.id, self._clock.now())
        replier = await self._replier(account, queue_id) if received.created else None
        if replier is not None:
            await self._auto.answer(replier, queue_id, mail, received.number, prefix)
        return 'created' if received.created else 'appended'

    async def _replier(self, account: EmailAccount | None, queue_id: str) -> EmailAccount | None:
        """Who acknowledges a new ticket: the receiving mailbox, or (for incoming mail only) the queue's account."""
        if account is None or account.sends:
            return account
        settings = await self._queues.find(account.tenant_id, queue_id)
        other = (
            await self._accounts.find(account.tenant_id, settings.account_id)
            if settings and settings.account_id
            else None
        )
        return other if other is not None and other.sends else None


class AutoReplier:
    """The queue's acknowledgement of a new ticket ("We got your message, number #1001"), never to robots."""

    def __init__(self, writer: Writer, vault: Vault, outbox: Outbox, limiter: RateLimiter, ids: IdGenerator) -> None:
        self._writer = writer
        self._vault = vault
        self._outbox = outbox
        self._limiter = limiter
        self._ids = ids

    async def answer(
        self, account: EmailAccount, queue_id: str, mail: ParsedEmail, number: int, prefix: str = DEFAULT_PREFIX
    ) -> None:
        if mail.automatic:
            return
        text = await self._writer.auto_reply(
            Context(
                tenant_id=account.tenant_id,
                queue_id=queue_id,
                ticket_number=number,
                ticket_subject=mail.subject,
                customer_name=mail.from_name,
                customer_email=mail.from_address,
            )
        )
        if text is None:
            return
        status = await self._limiter.hit(AUTO_REPLIES, f'{account.tenant_id}:{mail.from_address}')
        if not status.allowed:
            return
        subject, body = text
        try:
            await self._outbox.send(
                account,
                await self._vault.credential(account, 'smtp'),
                OutgoingMail(
                    sender=account.sender,
                    to=(mail.from_address,),
                    subject=f'{subject} {tagged(number, prefix)}' if tagged(number, prefix) not in subject else subject,
                    text=body,
                    message_id=f'<{self._ids.new_id()}@{account.address.split("@")[1]}>',
                    in_reply_to=mail.message_id,
                    references=(*mail.references, *([mail.message_id] if mail.message_id else [])),
                    automatic=True,
                ),
            )
        except MailboxError:
            logger.warning('The auto reply could not be sent', extra={'account': account.id})


@dataclass(frozen=True, kw_only=True)
class RetryFailedEmail(Command[Outcome]):
    tenant_id: str
    failed_id: str


class RetryFailedEmailHandler:
    def __init__(self, failed: FailedEmailRepository, process: ProcessEmailHandler) -> None:
        self._failed = failed
        self._process = process

    async def handle(self, command: RetryFailedEmail) -> Outcome:
        failed = await self._failed.find(command.tenant_id, command.failed_id)
        if failed is None:
            raise FailedEmailNotFoundError()
        await self._failed.delete(command.tenant_id, failed.id)
        account_id = failed.account_id
        return await self._process.handle(ProcessEmail(failed.tenant_id, account_id, failed.raw))


@dataclass(frozen=True, kw_only=True)
class DeleteFailedEmail(Command[None]):
    tenant_id: str
    failed_id: str


class DeleteFailedEmailHandler:
    def __init__(self, failed: FailedEmailRepository) -> None:
        self._failed = failed

    async def handle(self, command: DeleteFailedEmail) -> None:
        if await self._failed.find(command.tenant_id, command.failed_id) is None:
            raise FailedEmailNotFoundError()
        await self._failed.delete(command.tenant_id, command.failed_id)
