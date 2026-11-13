from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

type Connection = AsyncConnection[DictRow]


class Database:
    """
    A PostgreSQL connection pool. Repositories run their statements through
    `connection()`; inside `transaction()` they all share the transaction's connection,
    so a handler can make several repositories commit or roll back together.
    """

    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self._pool = AsyncConnectionPool[Connection](
            url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            connection_class=AsyncConnection[DictRow],
            kwargs={'autocommit': True, 'row_factory': dict_row},
        )
        self._current: ContextVar[Connection | None] = ContextVar(f'db-{id(self)}', default=None)

    async def open(self) -> None:
        """Connects; fails after 30 seconds without a reachable database."""
        await self._pool.open(wait=True, timeout=30)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Connection]:
        current = self._current.get()
        if current is not None:
            yield current
            return
        async with self._pool.connection() as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """A transaction, or a savepoint when one is already open."""
        current = self._current.get()
        if current is not None:
            async with current.transaction():
                yield
            return
        async with self._pool.connection() as connection, connection.transaction():
            token = self._current.set(connection)
            try:
                yield
            finally:
                self._current.reset(token)

    async def ping(self) -> bool:
        try:
            async with self.connection() as connection:
                await connection.execute('SELECT 1')
        except Exception:
            return False
        return True
