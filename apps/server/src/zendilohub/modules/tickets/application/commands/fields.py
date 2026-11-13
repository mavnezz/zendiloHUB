from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.transaction import TransactionManager

from ...domain.exceptions import ChecklistItemNotFoundError, FieldKeyTakenError, FieldNotFoundError, InvalidFieldError
from ...domain.models.actor import Actor
from ...domain.models.custom_field import FIELDS_MAX, ChecklistItem, CustomField, FieldKind
from ...domain.ports.repositories import ChecklistRepository, FieldRepository
from ...domain.ports.services import Presence
from ..services.desk import Desk, require


@dataclass(frozen=True, kw_only=True)
class SaveField(Command[CustomField]):
    """Creates (without `field_id`) or changes a field; its key and kind stay as they were made."""

    tenant_id: str
    key: str
    label: str
    kind: FieldKind
    options: tuple[str, ...] = ()
    field_id: str | None = None


class SaveFieldHandler:
    def __init__(self, fields: FieldRepository, ids: IdGenerator, clock: Clock) -> None:
        self._fields = fields
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveField) -> CustomField:
        existing = list(await self._fields.of_tenant(command.tenant_id))
        if command.field_id is None:
            if len(existing) >= FIELDS_MAX:
                raise InvalidFieldError('limit')
            if any(each.key == command.key for each in existing):
                raise FieldKeyTakenError()
            custom = CustomField(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                key=command.key,
                label=command.label,
                kind=command.kind,
                options=command.options,
                position=max((each.position for each in existing), default=0) + 1,
                created_at=self._clock.now(),
            )
        else:
            found = next((each for each in existing if each.id == command.field_id), None)
            if found is None:
                raise FieldNotFoundError()
            custom = found
            custom.label, custom.options = command.label, command.options
        custom.check()
        await self._fields.save(custom)
        return custom


@dataclass(frozen=True, kw_only=True)
class DeleteField(Command[CustomField]):
    tenant_id: str
    field_id: str


class DeleteFieldHandler:
    def __init__(self, fields: FieldRepository) -> None:
        self._fields = fields

    async def handle(self, command: DeleteField) -> CustomField:
        found = await self._fields.find(command.tenant_id, command.field_id)
        if found is None:
            raise FieldNotFoundError()
        await self._fields.delete(command.tenant_id, found.id)
        return found


@dataclass(frozen=True)
class ListFields(Query[Sequence[CustomField]]):
    tenant_id: str


class ListFieldsHandler:
    def __init__(self, fields: FieldRepository) -> None:
        self._fields = fields

    async def handle(self, query: ListFields) -> Sequence[CustomField]:
        return await self._fields.of_tenant(query.tenant_id)


@dataclass(frozen=True, kw_only=True)
class AddChecklistItem(Command[ChecklistItem]):
    tenant_id: str
    actor: Actor
    ticket_id: str
    text: str


class AddChecklistItemHandler:
    def __init__(self, desk: Desk, checklist: ChecklistRepository) -> None:
        self._desk = desk
        self._checklist = checklist

    async def handle(self, command: AddChecklistItem) -> ChecklistItem:
        ticket, rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        require(rights, 'edit')
        items = await self._checklist.of_ticket(ticket.tenant_id, ticket.id)
        if len(items) >= 100:
            raise InvalidFieldError('limit')
        item = ChecklistItem(
            id=self._desk.ids.new_id(),
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            text=command.text,
            done=False,
            position=max((each.position for each in items), default=0) + 1,
            created_at=self._desk.clock.now(),
        )
        item.check()
        await self._checklist.save(item)
        return item


@dataclass(frozen=True, kw_only=True)
class ChangeChecklistItem(Command[ChecklistItem]):
    """Ticks an item off (or on again), renames it, or deletes it (`delete`)."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    item_id: str
    done: bool | None = None
    text: str | None = None
    delete: bool = False


class ChangeChecklistItemHandler:
    def __init__(self, desk: Desk, checklist: ChecklistRepository, transactions: TransactionManager) -> None:
        self._desk = desk
        self._checklist = checklist
        self._transactions = transactions

    async def handle(self, command: ChangeChecklistItem) -> ChecklistItem:
        ticket, rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        require(rights, 'edit')
        item = await self._checklist.find(ticket.tenant_id, command.item_id)
        if item is None or item.ticket_id != ticket.id:
            raise ChecklistItemNotFoundError()
        if command.delete:
            await self._checklist.delete(ticket.tenant_id, item.id)
            return item
        if command.text is not None:
            item.text = command.text
        if command.done is not None:
            item.done = command.done
        item.check()
        await self._checklist.save(item)
        return item


@dataclass(frozen=True, kw_only=True)
class Checklist(Query[Sequence[ChecklistItem]]):
    tenant_id: str
    actor: Actor
    ticket_id: str


class ChecklistHandler:
    def __init__(self, desk: Desk, checklist: ChecklistRepository) -> None:
        self._desk = desk
        self._checklist = checklist

    async def handle(self, query: Checklist) -> Sequence[ChecklistItem]:
        ticket, _rights = await self._desk.load(query.tenant_id, query.actor, query.ticket_id)
        return await self._checklist.of_ticket(ticket.tenant_id, ticket.id)


@dataclass(frozen=True, kw_only=True)
class BeHere(Command[list[tuple[str, bool]]]):
    """The caller looks at a ticket (and writes in it); answers who else does."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    writing: bool = False


class BeHereHandler:
    def __init__(self, desk: Desk, presence: Presence) -> None:
        self._desk = desk
        self._presence = presence

    async def handle(self, command: BeHere) -> list[tuple[str, bool]]:
        ticket, _rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        return await self._presence.here(ticket.tenant_id, ticket.id, command.actor.user_id, writing=command.writing)
