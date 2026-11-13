from dataclasses import dataclass
from pathlib import Path

import pytest

from zendilohub.core.database.database import Connection, Database
from zendilohub.core.database.migration import SqlMigration, sql_migrations
from zendilohub.core.database.migrator import Migrator


@dataclass(frozen=True)
class Failing:
    name: str

    async def up(self, connection: Connection) -> None:
        await connection.execute('CREATE TABLE half_done (id INT)')
        raise RuntimeError('boom')


async def _tables(db: Database) -> list[str]:
    async with db.connection() as connection:
        rows = await (
            await connection.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        ).fetchall()
    return [str(row['tablename']) for row in rows]


USERS = SqlMigration('2026_10_22_000001_create_users_table', 'CREATE TABLE users (id INT); CREATE TABLE roles (id INT)')
PLANS = SqlMigration('2026_10_22_000002_create_plans_table', 'CREATE TABLE plans (id INT)')


async def test_runs_pending_migrations_in_name_order(empty_db: Database) -> None:
    migrator = Migrator(empty_db)

    assert await migrator.applied() == []
    assert await migrator.run([PLANS, USERS]) == [USERS.name, PLANS.name]
    assert await migrator.applied() == [USERS.name, PLANS.name]
    assert await _tables(empty_db) == ['migrations', 'plans', 'roles', 'users']


async def test_skips_applied_migrations_and_counts_batches(empty_db: Database) -> None:
    migrator = Migrator(empty_db)
    await migrator.run([USERS])

    assert await migrator.run([USERS, PLANS]) == [PLANS.name]
    assert await migrator.run([USERS, PLANS]) == []
    async with empty_db.connection() as connection:
        rows = await (await connection.execute('SELECT migration, batch FROM migrations ORDER BY id')).fetchall()
    assert [(row['migration'], row['batch']) for row in rows] == [(USERS.name, 1), (PLANS.name, 2)]


async def test_rolls_back_a_failing_migration(empty_db: Database) -> None:
    migrator = Migrator(empty_db)
    with pytest.raises(RuntimeError, match='boom'):
        await migrator.run([USERS, Failing('2026_10_22_000003_break_things')])

    assert await migrator.applied() == [USERS.name]
    assert 'half_done' not in await _tables(empty_db)


@pytest.mark.parametrize(
    ('migrations', 'message'),
    [
        ([SqlMigration('create_users', '')], 'Invalid migration name "create_users"'),
        ([USERS, USERS], f'Duplicate migration name "{USERS.name}"'),
    ],
)
async def test_validates_names(empty_db: Database, migrations: list[SqlMigration], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        await Migrator(empty_db).run(migrations)


def test_loads_sql_files_named_after_them(tmp_path: Path) -> None:
    (tmp_path / '2026_10_22_000002_b.sql').write_text('SELECT 2')
    (tmp_path / '2026_10_22_000001_a.sql').write_text('SELECT 1')
    (tmp_path / 'README.md').write_text('not a migration')

    assert sql_migrations(tmp_path) == [
        SqlMigration('2026_10_22_000001_a', 'SELECT 1'),
        SqlMigration('2026_10_22_000002_b', 'SELECT 2'),
    ]
