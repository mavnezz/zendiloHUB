import pytest

from zendilohub.core.database.database import Database


async def _count(db: Database) -> int:
    async with db.connection() as connection:
        row = await (await connection.execute('SELECT count(*) AS n FROM notes')).fetchone()
        assert row is not None
        return int(row['n'])


async def _insert(db: Database, text: str) -> None:
    async with db.connection() as connection:
        await connection.execute('INSERT INTO notes (text) VALUES (%s)', (text,))


async def _insert_and_fail(db: Database, text: str) -> None:
    async with db.transaction():
        await _insert(db, text)
        raise RuntimeError('boom')


@pytest.fixture
async def db(empty_db: Database) -> Database:
    async with empty_db.connection() as connection:
        await connection.execute('CREATE TABLE notes (text TEXT NOT NULL)')
    return empty_db


async def test_statements_outside_a_transaction_commit_right_away(db: Database) -> None:
    await _insert(db, 'a')
    assert await _count(db) == 1


async def test_a_transaction_commits_everything_together(db: Database) -> None:
    async with db.transaction():
        await _insert(db, 'a')
        await _insert(db, 'b')
    assert await _count(db) == 2


async def test_a_failed_transaction_rolls_everything_back(db: Database) -> None:
    with pytest.raises(RuntimeError):
        await _insert_and_fail(db, 'a')
    assert await _count(db) == 0


async def test_a_nested_transaction_is_a_savepoint(db: Database) -> None:
    async with db.transaction():
        await _insert(db, 'outer')
        with pytest.raises(RuntimeError):
            await _insert_and_fail(db, 'inner')
    assert await _count(db) == 1


async def test_pings(db: Database) -> None:
    assert await db.ping()


async def test_ping_fails_without_a_database() -> None:
    db = Database('postgresql://nobody:nothing@127.0.0.1:1/none')
    assert not await db.ping()
