from dataclasses import dataclass

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager
from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import QueueDeleted

from ...domain.exceptions import QueueHasTicketsError, QueueLimitError, QueueNameTakenError, QueueNotFoundError
from ...domain.models.queue import QUEUES_MAX, Queue
from ...domain.ports.repositories import QueueRepository, QueueUsage


@dataclass(frozen=True, kw_only=True)
class CreateQueue(Command[Queue]):
    tenant_id: str
    name: str
    description: str = ''


class CreateQueueHandler:
    def __init__(self, queues: QueueRepository, ids: IdGenerator, clock: Clock) -> None:
        self._queues = queues
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateQueue) -> Queue:
        queue = Queue.create(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=command.name,
            description=command.description,
            now=self._clock.now(),
        )
        if await self._queues.count(command.tenant_id) >= QUEUES_MAX:
            raise QueueLimitError(QUEUES_MAX)
        if await self._queues.name_taken(command.tenant_id, queue.name):
            raise QueueNameTakenError()
        await self._queues.save(queue)
        return queue


@dataclass(frozen=True, kw_only=True)
class UpdateQueue(Command[Queue]):
    tenant_id: str
    queue_id: str
    name: str
    description: str = ''


class UpdateQueueHandler:
    def __init__(self, queues: QueueRepository, clock: Clock) -> None:
        self._queues = queues
        self._clock = clock

    async def handle(self, command: UpdateQueue) -> Queue:
        queue = await self._queues.find(command.tenant_id, command.queue_id)
        if queue is None:
            raise QueueNotFoundError()
        queue.change(name=command.name, description=command.description, now=self._clock.now())
        if await self._queues.name_taken(command.tenant_id, queue.name, except_id=queue.id):
            raise QueueNameTakenError()
        await self._queues.save(queue)
        return queue


@dataclass(frozen=True, kw_only=True)
class DeleteQueue(Command[Queue]):
    """With the rights on it; `QueueDeleted` lets other modules clean up in the same transaction."""

    tenant_id: str
    queue_id: str


class DeleteQueueHandler:
    def __init__(
        self, queues: QueueRepository, usage: QueueUsage, transactions: TransactionManager, events: EventBus
    ) -> None:
        self._usage = usage
        self._queues = queues
        self._transactions = transactions
        self._events = events

    async def handle(self, command: DeleteQueue) -> Queue:
        queue = await self._queues.find(command.tenant_id, command.queue_id)
        if queue is None:
            raise QueueNotFoundError()
        tickets = await self._usage.in_queue(queue.tenant_id, queue.id)
        if tickets:
            raise QueueHasTicketsError(tickets)
        async with self._transactions.transaction():
            await self._events.publish(QueueDeleted(tenant_id=queue.tenant_id, queue_id=queue.id))
            await self._queues.delete(queue.tenant_id, queue.id)
        return queue
