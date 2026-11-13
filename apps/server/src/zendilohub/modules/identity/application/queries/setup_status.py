from dataclasses import dataclass

from zendilohub.core.bus.message import Query

from ...domain.ports.user_repository import UserRepository


@dataclass(frozen=True)
class GetSetupStatus(Query[bool]):
    """Whether the setup wizard is open: a self-hosted instance without an administrator."""


class GetSetupStatusHandler:
    def __init__(self, users: UserRepository, *, self_hosted: bool) -> None:
        self._users = users
        self._self_hosted = self_hosted

    async def handle(self, query: GetSetupStatus) -> bool:
        return self._self_hosted and await self._users.count_admins() == 0
