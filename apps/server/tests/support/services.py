"""
PostgreSQL and Redis for the tests: started once per session in Docker (testcontainers),
or taken from ZENDILOHUB_TEST_DATABASE_URL / ZENDILOHUB_TEST_REDIS_URL.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import psycopg


@dataclass(frozen=True)
class Services:
    database_url: str
    """A maintenance database; tests create their own databases next to it."""
    redis_url: str

    def database(self, name: str) -> str:
        parts = urlsplit(self.database_url)
        return urlunsplit(parts._replace(path=f'/{name}'))

    def create_database(self, name: str, template: str | None = None) -> str:
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'.encode())
            suffix = f' TEMPLATE "{template}" STRATEGY FILE_COPY' if template else ''
            connection.execute(f'CREATE DATABASE "{name}"{suffix}'.encode())
        return self.database(name)

    def drop_database(self, name: str) -> None:
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'.encode())


@contextmanager
def start_services() -> Iterator[Services]:
    database_url = os.environ.get('ZENDILOHUB_TEST_DATABASE_URL')
    redis_url = os.environ.get('ZENDILOHUB_TEST_REDIS_URL')
    if database_url and redis_url:
        yield Services(database_url, redis_url)
        return

    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

    with (
        PostgresContainer('pgvector/pgvector:pg18', driver=None) as postgres,
        RedisContainer('redis:8-alpine') as redis,
    ):
        host = redis.get_container_host_ip()
        port = redis.get_exposed_port(6379)
        yield Services(postgres.get_connection_url(), f'redis://{host}:{port}/0')
