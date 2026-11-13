from dataclasses import dataclass

from zendilohub.core.bus.message import Query

from ...domain.exceptions import UserNotFoundError
from ...domain.models.user import User
from ...domain.ports.user_repository import UserPage, UserRepository


@dataclass(frozen=True)
class GetUser(Query[User]):
    user_id: str


@dataclass(frozen=True, kw_only=True)
class SearchUsers(Query[UserPage]):
    query: str = ''
    offset: int = 0
    limit: int = 50
    ids: tuple[str, ...] = ()


class GetUserHandler:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def handle(self, query: GetUser) -> User:
        user = await self._users.find(query.user_id)
        if user is None:
            raise UserNotFoundError()
        return user


class SearchUsersHandler:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def handle(self, query: SearchUsers) -> UserPage:
        return await self._users.search(
            query.query.strip().lower(), offset=query.offset, limit=query.limit, ids=query.ids
        )
