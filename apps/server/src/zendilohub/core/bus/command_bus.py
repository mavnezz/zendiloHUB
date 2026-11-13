from typing import Any, Self, cast

from .message import Command, Handler, Message, Query


class CommandBus:
    """
    Maps each command/query class to exactly one handler. Every module owns its
    own bus, so a module's UI can only dispatch that module's messages.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, Handler[Any, Any]] = {}

    def register[M: Message](self, message_type: type[M], handler: Handler[M, Any]) -> Self:
        if message_type in self._handlers:
            raise ValueError(f'A handler for {message_type.__name__} is already registered')
        self._handlers[message_type] = handler
        return self

    async def execute[R](self, command: Command[R]) -> R:
        return cast(R, await self._dispatch(command))

    async def query[R](self, query: Query[R]) -> R:
        return cast(R, await self._dispatch(query))

    async def _dispatch(self, message: Message) -> Any:
        handler = self._handlers.get(type(message))
        if handler is None:
            raise LookupError(f'No handler registered for {type(message).__name__}')
        return await handler.handle(message)
