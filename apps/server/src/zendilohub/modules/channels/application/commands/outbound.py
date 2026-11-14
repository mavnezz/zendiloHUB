from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.jobs import JobQueue

from ...domain.models.email import reply_subject
from ...domain.models.records import Delivery, DeliveryStatus
from ...domain.ports.repositories import AccountRepository, DeliveryRepository, QueueChannelRepository
from ...domain.ports.services import MailboxError, Outbox, OutgoingMail, Tickets
from .accounts import Vault

SEND_TASK = 'channels.send'
ATTEMPTS_MAX = 5
RETRY_SECONDS = (60, 300, 900, 3600)


@dataclass(frozen=True)
class QueueReply(Command[None]):
    """A reply of the team was written: it goes out by e-mail in the background."""

    tenant_id: str
    ticket_id: str
    message_id: str


class QueueReplyHandler:
    def __init__(self, deliveries: DeliveryRepository, jobs: JobQueue, clock: Clock) -> None:
        self._deliveries = deliveries
        self._jobs = jobs
        self._clock = clock

    async def handle(self, command: QueueReply) -> None:
        await self._deliveries.save(
            Delivery(
                message_id=command.message_id,
                tenant_id=command.tenant_id,
                ticket_id=command.ticket_id,
                status='queued',
                account_id=None,
                error=None,
                attempts=0,
                updated_at=self._clock.now(),
            )
        )
        await self._jobs.enqueue(SEND_TASK, command.tenant_id, command.message_id)


@dataclass(frozen=True)
class SendReply(Command[DeliveryStatus]):
    tenant_id: str
    message_id: str


class SendReplyHandler:
    """Sends a reply from the account of the ticket's queue to the customer, in the thread of the ticket's e-mails."""

    def __init__(
        self,
        deliveries: DeliveryRepository,
        queues: QueueChannelRepository,
        accounts: AccountRepository,
        vault: Vault,
        outbox: Outbox,
        tickets: Tickets,
        jobs: JobQueue,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._deliveries = deliveries
        self._queues = queues
        self._accounts = accounts
        self._vault = vault
        self._outbox = outbox
        self._tickets = tickets
        self._jobs = jobs
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SendReply) -> DeliveryStatus:
        delivery = await self._deliveries.find(command.tenant_id, command.message_id)
        reply = await self._tickets.outgoing(command.tenant_id, command.message_id)
        if delivery is None or reply is None or delivery.status == 'sent':
            return delivery.status if delivery else 'skipped'
        settings = await self._queues.find(command.tenant_id, reply.queue_id)
        account = (
            await self._accounts.find(command.tenant_id, settings.account_id)
            if settings and settings.account_id
            else None
        )
        if reply.customer_email is None:
            return await self._finish(delivery, 'skipped', 'no_customer_address')
        if account is None:
            return await self._finish(delivery, 'skipped', 'no_account')
        delivery.account_id = account.id
        message_id = f'<{self._ids.new_id()}@{account.address.split("@")[1]}>'
        try:
            await self._outbox.send(
                account,
                await self._vault.credential(account, 'smtp'),
                OutgoingMail(
                    sender=account.sender,
                    to=(reply.customer_email,),
                    subject=reply_subject(
                        reply.subject, reply.number, await self._tickets.subject_prefix(command.tenant_id)
                    ),
                    text=reply.body,
                    message_id=message_id,
                    in_reply_to=reply.references[-1] if reply.references else None,
                    references=reply.references,
                    attachments=reply.attachments,
                ),
            )
        except MailboxError as error:
            delivery.attempts += 1
            if delivery.attempts < ATTEMPTS_MAX:
                delay = RETRY_SECONDS[min(delivery.attempts, len(RETRY_SECONDS)) - 1]
                await self._jobs.enqueue(SEND_TASK, command.tenant_id, command.message_id, delay=delay)
                return await self._finish(delivery, 'queued', str(error) or 'failed')
            return await self._finish(delivery, 'failed', str(error) or 'failed')
        await self._tickets.mark_sent(
            command.tenant_id,
            command.message_id,
            email_message_id=message_id,
            from_address=account.address,
            to=(reply.customer_email,),
        )
        return await self._finish(delivery, 'sent', None)

    async def _finish(self, delivery: Delivery, status: DeliveryStatus, error: str | None) -> DeliveryStatus:
        delivery.status, delivery.error, delivery.updated_at = status, error, self._clock.now()
        await self._deliveries.save(delivery)
        return status


@dataclass(frozen=True, kw_only=True)
class ResendReply(Command[None]):
    """Tries a failed reply again (the button next to it)."""

    tenant_id: str
    message_id: str


class ResendReplyHandler:
    def __init__(self, deliveries: DeliveryRepository, jobs: JobQueue, clock: Clock) -> None:
        self._deliveries = deliveries
        self._jobs = jobs
        self._clock = clock

    async def handle(self, command: ResendReply) -> None:
        delivery = await self._deliveries.find(command.tenant_id, command.message_id)
        if delivery is None or delivery.status == 'sent':
            return
        delivery.status, delivery.attempts, delivery.error = 'queued', 0, None
        delivery.updated_at = self._clock.now()
        await self._deliveries.save(delivery)
        await self._jobs.enqueue(SEND_TASK, command.tenant_id, command.message_id)
