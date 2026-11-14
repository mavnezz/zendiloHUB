import hashlib
import secrets
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.contact_card import ContactCard
from zendilohub.core.domain.email_address import normalized_email
from zendilohub.core.domain.mailer import Mailer, MailMessage
from zendilohub.core.domain.portal import PortalThread, PortalTicket
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

from ...domain.models.portal import (
    LINK_LIFETIME,
    SESSION_LIFETIME,
    InvalidPortalError,
    PortalClosedError,
    PortalLinkInvalidError,
    PortalLogin,
    PortalLoginRequiredError,
    PortalSettings,
    PortalTicketNotFoundError,
)
from ...domain.ports.repositories import Customers, PortalRepository, Tickets

LINKS = RateLimit('portal-links', limit=5, window_seconds=60 * 60)


def hash_of(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class SaveSettings(Command[PortalSettings]):
    settings: PortalSettings


class SaveSettingsHandler:
    def __init__(self, portal: PortalRepository) -> None:
        self._portal = portal

    async def handle(self, command: SaveSettings) -> PortalSettings:
        command.settings.check()
        await self._portal.save_settings(command.settings)
        return command.settings


@dataclass(frozen=True)
class GetSettings(Query[PortalSettings]):
    tenant_id: str


class GetSettingsHandler:
    def __init__(self, portal: PortalRepository) -> None:
        self._portal = portal

    async def handle(self, query: GetSettings) -> PortalSettings:
        return await self._portal.settings(query.tenant_id)


@dataclass(frozen=True, kw_only=True)
class RequestLink(Command[None]):
    """Sends a sign-in link to a known contact's address; says nothing about whether the address is known."""

    tenant_id: str
    email: str
    link_base: str


class RequestLinkHandler:
    def __init__(
        self,
        portal: PortalRepository,
        customers: Customers,
        mailer: Mailer,
        limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._portal = portal
        self._customers = customers
        self._mailer = mailer
        self._limiter = limiter
        self._clock = clock

    async def handle(self, command: RequestLink) -> None:
        settings = await self._portal.settings(command.tenant_id)
        if not settings.enabled:
            raise PortalClosedError()
        email = normalized_email(command.email)
        if email is None or not (await self._limiter.hit(LINKS, f'{command.tenant_id}:{email}')).allowed:
            return
        contact = await self._customers.by_email(command.tenant_id, email)
        if contact is None:
            return
        token = secrets.token_urlsafe(32)
        await self._portal.remove_expired(self._clock.now())
        await self._portal.add_login(
            'link',
            PortalLogin(
                token_hash=hash_of(token),
                tenant_id=command.tenant_id,
                contact_id=contact.id,
                email=email,
                expires_at=self._clock.now() + LINK_LIFETIME,
            ),
        )
        link = f'{command.link_base}/portal/{command.tenant_id}/verify?token={token}'
        await self._mailer.send(
            MailMessage(
                to=email,
                subject='Your sign-in link / Ihr Anmeldelink',
                text=(
                    f'Hello {contact.name},\n\nsign in to see your requests:\n{link}\n\nThe link works for 30 minutes.'
                    f'\n\n---\n\nHallo {contact.name},\n\nmelden Sie sich an, um Ihre Anfragen zu sehen:\n{link}\n\n'
                    'Der Link gilt 30 Minuten.\n'
                ),
            )
        )


@dataclass(frozen=True)
class SignedIn:
    token: str
    contact: ContactCard


@dataclass(frozen=True)
class Verify(Command[SignedIn]):
    """Trades a sign-in link (once) for a session."""

    token: str


class VerifyHandler:
    def __init__(self, portal: PortalRepository, customers: Customers, clock: Clock) -> None:
        self._portal = portal
        self._customers = customers
        self._clock = clock

    async def handle(self, command: Verify) -> SignedIn:
        now = self._clock.now()
        link = await self._portal.find_login('link', hash_of(command.token), now)
        if link is None:
            raise PortalLinkInvalidError()
        await self._portal.remove_login('link', link.token_hash)
        contact = await self._customers.card(link.tenant_id, link.contact_id)
        if contact is None or not (await self._portal.settings(link.tenant_id)).enabled:
            raise PortalLinkInvalidError()
        token = secrets.token_urlsafe(32)
        await self._portal.add_login(
            'session',
            PortalLogin(
                token_hash=hash_of(token),
                tenant_id=link.tenant_id,
                contact_id=link.contact_id,
                email=link.email,
                expires_at=now + SESSION_LIFETIME,
            ),
        )
        return SignedIn(token, contact)


@dataclass(frozen=True)
class Visitor:
    """A signed-in customer and the contacts whose tickets they see."""

    tenant_id: str
    contact: ContactCard
    contact_ids: list[str]
    settings: PortalSettings


@dataclass(frozen=True)
class WhoIs(Query[Visitor]):
    tenant_id: str
    token: str


class WhoIsHandler:
    def __init__(self, portal: PortalRepository, customers: Customers, clock: Clock) -> None:
        self._portal = portal
        self._customers = customers
        self._clock = clock

    async def handle(self, query: WhoIs) -> Visitor:
        session = (
            await self._portal.find_login('session', hash_of(query.token), self._clock.now()) if query.token else None
        )
        if session is None or session.tenant_id != query.tenant_id:
            raise PortalLoginRequiredError()
        settings = await self._portal.settings(query.tenant_id)
        contact = await self._customers.card(query.tenant_id, session.contact_id)
        if contact is None or not settings.enabled:
            raise PortalLoginRequiredError()
        ids = [contact.id]
        if settings.company_tickets and contact.company_id:
            ids = sorted({*ids, *await self._customers.of_company(query.tenant_id, contact.company_id)})
        return Visitor(query.tenant_id, contact, ids, settings)


@dataclass(frozen=True)
class SignOut(Command[None]):
    token: str


class SignOutHandler:
    def __init__(self, portal: PortalRepository) -> None:
        self._portal = portal

    async def handle(self, command: SignOut) -> None:
        await self._portal.remove_login('session', hash_of(command.token))


@dataclass(frozen=True)
class MyTickets(Query[list[PortalTicket]]):
    visitor: Visitor


class MyTicketsHandler:
    def __init__(self, tickets: Tickets) -> None:
        self._tickets = tickets

    async def handle(self, query: MyTickets) -> list[PortalTicket]:
        return await self._tickets.tickets_of(query.visitor.tenant_id, query.visitor.contact_ids)


@dataclass(frozen=True)
class MyThread(Query[PortalThread]):
    visitor: Visitor
    ticket_id: str


class MyThreadHandler:
    def __init__(self, tickets: Tickets) -> None:
        self._tickets = tickets

    async def handle(self, query: MyThread) -> PortalThread:
        found = await self._tickets.thread(query.visitor.tenant_id, query.visitor.contact_ids, query.ticket_id)
        if found is None:
            raise PortalTicketNotFoundError()
        return found


@dataclass(frozen=True)
class Answer(Command[PortalThread]):
    visitor: Visitor
    ticket_id: str
    body: str


class AnswerHandler:
    def __init__(self, tickets: Tickets) -> None:
        self._tickets = tickets

    async def handle(self, command: Answer) -> PortalThread:
        visitor = command.visitor
        body = command.body.strip()
        if not body or len(body) > 50_000:
            raise InvalidPortalError('body')
        if not await self._tickets.reply(
            visitor.tenant_id, visitor.contact.id, visitor.contact_ids, command.ticket_id, body
        ):
            raise PortalTicketNotFoundError()
        thread = await self._tickets.thread(visitor.tenant_id, visitor.contact_ids, command.ticket_id)
        assert thread is not None
        return thread


@dataclass(frozen=True)
class OpenTicket(Command[PortalTicket]):
    visitor: Visitor
    subject: str
    body: str


class OpenTicketHandler:
    def __init__(self, tickets: Tickets) -> None:
        self._tickets = tickets

    async def handle(self, command: OpenTicket) -> PortalTicket:
        visitor = command.visitor
        subject, body = ' '.join(command.subject.split()), command.body.strip()
        if not 1 <= len(subject) <= 250:
            raise InvalidPortalError('subject')
        if not body or len(body) > 50_000:
            raise InvalidPortalError('body')
        assert visitor.settings.queue_id is not None
        return await self._tickets.open(visitor.tenant_id, visitor.contact.id, visitor.settings.queue_id, subject, body)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, portal: PortalRepository) -> None:
        self._portal = portal

    async def handle(self, command: ForgetTenant) -> None:
        await self._portal.forget_tenant(command.tenant_id)
