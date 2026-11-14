from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query

from ...domain.models.numbering import InvalidNumberingError, Numbering
from ..services.desk import Desk


@dataclass(frozen=True, kw_only=True)
class NumberingView:
    numbering: Numbering
    next_number: int
    """The number the next ticket gets (nothing is handed out for the preview)."""


@dataclass(frozen=True)
class GetNumbering(Query[NumberingView]):
    tenant_id: str


@dataclass(frozen=True)
class SaveNumbering(Command[NumberingView]):
    numbering: Numbering


@dataclass(frozen=True)
class SubjectPrefix(Query[str]):
    tenant_id: str


async def _view(desk: Desk, numbering: Numbering) -> NumberingView:
    counter = await desk.tickets.counter(numbering.tenant_id)
    number, _ = numbering.issue(counter, await desk.today(numbering.tenant_id))
    return NumberingView(numbering=numbering, next_number=number)


class GetNumberingHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: GetNumbering) -> NumberingView:
        return await _view(self._desk, await self._desk.numberings.find(query.tenant_id))


class SaveNumberingHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, command: SaveNumbering) -> NumberingView:
        numbering = command.numbering
        numbering.check()
        before = await self._desk.numberings.find(numbering.tenant_id)
        counter = await self._desk.tickets.counter(numbering.tenant_id)
        # Numbers only grow: a start at or below the last number would never be used.
        if numbering.format == 'increment' and numbering.start != before.start and numbering.start <= counter.last:
            raise InvalidNumberingError('start', {'minimum': counter.last + 1})
        numbering.updated_at = self._desk.clock.now()
        await self._desk.numberings.save(numbering)
        return await _view(self._desk, numbering)


class SubjectPrefixHandler:
    def __init__(self, desk: Desk) -> None:
        self._desk = desk

    async def handle(self, query: SubjectPrefix) -> str:
        return (await self._desk.numberings.find(query.tenant_id)).prefix
