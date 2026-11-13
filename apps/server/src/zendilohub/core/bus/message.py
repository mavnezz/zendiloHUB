from typing import Any, Protocol


class Command[R]:
    """A command changes state. `R` is the handler's result type: `bus.execute(XCommand())` is typed by it."""


class Query[R]:
    """A query reads state and never changes it."""


type Message = Command[Any] | Query[Any]


class Handler[M, R](Protocol):
    async def handle(self, message: M, /) -> R: ...
