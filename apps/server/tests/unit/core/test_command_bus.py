from dataclasses import dataclass

import pytest

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.bus.message import Command, Query


@dataclass(frozen=True)
class Greet(Command[str]):
    name: str


@dataclass(frozen=True)
class CountGreetings(Query[int]):
    pass


class GreetHandler:
    def __init__(self) -> None:
        self.count = 0

    async def handle(self, command: Greet) -> str:
        self.count += 1
        return f'Hello, {command.name}'


class CountHandler:
    def __init__(self, greet: GreetHandler) -> None:
        self.greet = greet

    async def handle(self, _query: CountGreetings) -> int:
        return self.greet.count


async def test_dispatches_commands_and_queries_to_their_handlers() -> None:
    greet = GreetHandler()
    bus = CommandBus().register(Greet, greet).register(CountGreetings, CountHandler(greet))

    assert await bus.execute(Greet('Ada')) == 'Hello, Ada'
    assert await bus.query(CountGreetings()) == 1


async def test_rejects_a_second_handler_for_the_same_message() -> None:
    bus = CommandBus().register(Greet, GreetHandler())
    with pytest.raises(ValueError, match='already registered'):
        bus.register(Greet, GreetHandler())


async def test_fails_for_messages_without_handler() -> None:
    with pytest.raises(LookupError, match='No handler registered for Greet'):
        await CommandBus().execute(Greet('Ada'))
