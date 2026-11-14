from dataclasses import dataclass

from zendilohub.core.bus.message import Query
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

from ...domain.exceptions import AssistantBusyError, AssistantOffError
from ...domain.models.actor import Actor
from ...domain.models.assist import AssistInput, AssistLine, AssistTask
from ...domain.ports.repositories import MessageRepository
from ...domain.ports.services import CustomerDirectory, TicketWriter
from ..services.desk import Desk

# Each request costs money: a person may ask 30 times an hour, an organization 300 times.
PER_PERSON = RateLimit('assist-person', limit=30, window_seconds=60 * 60)
PER_TENANT = RateLimit('assist-tenant', limit=300, window_seconds=60 * 60)
LAST_MESSAGES = 30
"""Long tickets: the model reads the latest messages (and the first one, which says what it is about)."""
LINE_MAX = 8_000


@dataclass(frozen=True, kw_only=True)
class AssistantStatus(Query[bool]):
    """Whether the AI assistant is set up (the web app hides its buttons otherwise)."""


class AssistantStatusHandler:
    def __init__(self, writer: TicketWriter) -> None:
        self._writer = writer

    async def handle(self, query: AssistantStatus) -> bool:
        return self._writer.enabled


@dataclass(frozen=True, kw_only=True)
class Assist(Query[str]):
    """A summary of the ticket or a draft reply; nothing is saved, the agent decides what to do with it."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    task: AssistTask


class AssistHandler:
    def __init__(
        self,
        desk: Desk,
        messages: MessageRepository,
        customers: CustomerDirectory,
        writer: TicketWriter,
        limiter: RateLimiter,
    ) -> None:
        self._desk = desk
        self._messages = messages
        self._customers = customers
        self._writer = writer
        self._limiter = limiter

    async def handle(self, query: Assist) -> str:
        if not self._writer.enabled:
            raise AssistantOffError()
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, query.ticket_id)
        for limit, subject in ((PER_PERSON, f'{query.tenant_id}:{query.actor.user_id}'), (PER_TENANT, query.tenant_id)):
            status = await self._limiter.hit(limit, subject)
            if not status.allowed:
                raise AssistantBusyError(status.retry_after)
        messages = list(await self._messages.of_ticket(ticket.tenant_id, ticket.id))
        if len(messages) > LAST_MESSAGES:
            messages = [messages[0], *messages[-(LAST_MESSAGES - 1) :]]
        _address, customer = await self._customers.address_of(ticket.tenant_id, ticket.customer_id)
        return await self._writer.write(
            AssistInput(
                task=query.task,
                subject=ticket.subject,
                customer=customer or None,
                lines=tuple(
                    AssistLine(
                        author=each.author_name,
                        from_customer=each.direction == 'in',
                        internal=each.kind == 'internal',
                        body=each.body[:LINE_MAX],
                    )
                    for each in messages
                ),
                agent=query.actor.name,
            )
        )
