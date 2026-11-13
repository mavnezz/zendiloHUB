from dataclasses import dataclass
from datetime import timedelta

from zendilohub.core.bus.message import Command
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.models.audit_entry import AuditEntry
from ...domain.ports.audit_repository import AuditRepository


@dataclass(frozen=True, kw_only=True)
class RecordAction(Command[AuditEntry]):
    action: str
    tenant_id: str | None
    target: str | None
    actor_id: str | None
    actor_email: str | None
    succeeded: bool
    status: int
    client: str | None


class RecordActionHandler:
    def __init__(self, entries: AuditRepository, ids: IdGenerator, clock: Clock) -> None:
        self._entries = entries
        self._ids = ids
        self._clock = clock

    async def handle(self, command: RecordAction) -> AuditEntry:
        entry = AuditEntry(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            actor_id=command.actor_id,
            actor_email=command.actor_email,
            action=command.action,
            target=command.target[:500] if command.target else None,
            succeeded=command.succeeded,
            status=command.status,
            client=command.client,
            created_at=self._clock.now(),
        )
        await self._entries.add(entry)
        return entry


@dataclass(frozen=True)
class PurgeAuditLog(Command[int]):
    """Deletes entries older than the retention period; returns how many."""

    retention_days: int


class PurgeAuditLogHandler:
    def __init__(self, entries: AuditRepository, clock: Clock) -> None:
        self._entries = entries
        self._clock = clock

    async def handle(self, command: PurgeAuditLog) -> int:
        return await self._entries.delete_before(self._clock.now() - timedelta(days=command.retention_days))


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, entries: AuditRepository) -> None:
        self._entries = entries

    async def handle(self, command: ForgetTenant) -> None:
        await self._entries.delete_for_tenant(command.tenant_id)


@dataclass(frozen=True)
class ForgetActor(Command[None]):
    user_id: str
    email: str


class ForgetActorHandler:
    def __init__(self, entries: AuditRepository) -> None:
        self._entries = entries

    async def handle(self, command: ForgetActor) -> None:
        await self._entries.forget_actor(command.user_id, command.email)
