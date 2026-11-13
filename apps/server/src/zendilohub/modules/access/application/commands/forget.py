from dataclasses import dataclass

from zendilohub.core.bus.message import Command

from ...domain.ports.repositories import GroupRepository, TenantData


@dataclass(frozen=True)
class ForgetMember(Command[None]):
    """Someone left the organization: they leave its groups."""

    tenant_id: str
    user_id: str


class ForgetMemberHandler:
    def __init__(self, groups: GroupRepository) -> None:
        self._groups = groups

    async def handle(self, command: ForgetMember) -> None:
        await self._groups.remove_member(command.tenant_id, command.user_id)


@dataclass(frozen=True)
class ForgetUser(Command[None]):
    """An account was deleted: it leaves every group."""

    user_id: str


class ForgetUserHandler:
    def __init__(self, groups: GroupRepository) -> None:
        self._groups = groups

    async def handle(self, command: ForgetUser) -> None:
        await self._groups.remove_user(command.user_id)


@dataclass(frozen=True)
class ForgetTenant(Command[None]):
    tenant_id: str


class ForgetTenantHandler:
    def __init__(self, data: TenantData) -> None:
        self._data = data

    async def handle(self, command: ForgetTenant) -> None:
        await self._data.forget(command.tenant_id)
