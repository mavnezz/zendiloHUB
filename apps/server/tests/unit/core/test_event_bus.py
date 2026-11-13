from dataclasses import dataclass

from zendilohub.core.events.event_bus import EventBus
from zendilohub.core.events.integration_events import IntegrationEvent


@dataclass(frozen=True, kw_only=True)
class SomethingHappened(IntegrationEvent):
    what: str


@dataclass(frozen=True, kw_only=True)
class SomethingElse(IntegrationEvent):
    pass


async def test_delivers_events_to_their_listeners_in_order() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def first(event: SomethingHappened) -> None:
        seen.append(f'first {event.what}')

    async def second(event: SomethingHappened) -> None:
        seen.append(f'second {event.what}')

    async def other(_event: SomethingElse) -> None:
        seen.append('other')

    bus.subscribe(SomethingHappened, first)
    bus.subscribe(SomethingHappened, second)
    bus.subscribe(SomethingElse, other)
    await bus.publish(SomethingHappened(what='it'))

    assert seen == ['first it', 'second it']


async def test_unsubscribes() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def listener(event: SomethingHappened) -> None:
        seen.append(event.what)

    unsubscribe = bus.subscribe(SomethingHappened, listener)
    unsubscribe()
    unsubscribe()
    await bus.publish(SomethingHappened(what='it'))

    assert seen == []


async def test_publishing_without_listeners_does_nothing() -> None:
    await EventBus().publish(SomethingElse())
