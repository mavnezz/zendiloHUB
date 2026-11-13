from collections.abc import Awaitable, Callable

from .integration_events import IntegrationEvent

type Listener[E: IntegrationEvent] = Callable[[E], Awaitable[None]]


class EventBus:
    """
    In-process event bus: `publish` resolves once every listener ran, in the order
    they subscribed. Listeners run inside the publisher's transaction, if there is one.
    """

    def __init__(self) -> None:
        self._listeners: dict[type[IntegrationEvent], list[Listener[IntegrationEvent]]] = {}

    def subscribe[E: IntegrationEvent](self, event_type: type[E], listener: Listener[E]) -> Callable[[], None]:
        listeners = self._listeners.setdefault(event_type, [])
        # Stored untyped: `publish` only ever passes events of exactly `event_type`.
        listeners.append(listener)  # type: ignore[arg-type]

        def unsubscribe() -> None:
            if listener in listeners:
                listeners.remove(listener)

        return unsubscribe

    async def publish(self, event: IntegrationEvent) -> None:
        for listener in list(self._listeners.get(type(event), [])):
            await listener(event)
