from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .database import Connection


class Migration(Protocol):
    """
    A forward-only schema change. Names follow Laravel's convention
    (`2026_10_22_000001_create_users_table`) and define the execution order across all modules.
    """

    @property
    def name(self) -> str: ...

    async def up(self, connection: Connection) -> None: ...


@dataclass(frozen=True)
class SqlMigration:
    name: str
    sql: str

    async def up(self, connection: Connection) -> None:
        await connection.execute(self.sql.encode())


def sql_migrations(directory: Path) -> list[SqlMigration]:
    """Every `*.sql` file in a module's `infrastructure/migrations/` directory, named after the file."""
    return [SqlMigration(path.stem, path.read_text('utf-8')) for path in sorted(directory.glob('*.sql'))]
