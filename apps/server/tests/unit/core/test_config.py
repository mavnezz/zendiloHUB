from pathlib import Path

import pytest

from zendilohub.core.config import PRIVATE_NETWORKS, InitialAdmin, load_config


def test_has_sensible_defaults() -> None:
    config = load_config({})

    assert config.host == '0.0.0.0'
    assert config.port == 8080
    assert config.log_level == 'info'
    assert config.database_url == 'postgresql://zendilohub:zendilohub@localhost:5432/zendilohub'
    assert config.redis_url == 'redis://localhost:6379/0'
    assert config.data_dir == Path('data').resolve()
    assert config.web_dir is None
    assert config.public_url is None
    assert config.trusted_proxies == PRIVATE_NETWORKS
    assert config.api_docs is True
    assert config.max_upload_bytes == 25 * 1024 * 1024
    assert config.audit_retention_days == 365
    assert config.multi_tenant is False
    assert config.initial_admin is None


def test_reads_the_environment() -> None:
    config = load_config(
        {
            'ZENDILOHUB_HOST': '127.0.0.1',
            'ZENDILOHUB_PORT': '9000',
            'ZENDILOHUB_LOG_LEVEL': 'DEBUG',
            'ZENDILOHUB_DATABASE_URL': 'postgresql://db/zendilohub',
            'ZENDILOHUB_REDIS_URL': 'redis://cache:6379/1',
            'ZENDILOHUB_DATA_DIR': '/data',
            'ZENDILOHUB_WEB_DIR': '/app/web',
            'ZENDILOHUB_PUBLIC_URL': 'https://app.zendilohub.example/',
            'ZENDILOHUB_TRUSTED_PROXIES': '10.0.0.1',
            'ZENDILOHUB_API_DOCS': 'off',
            'ZENDILOHUB_MAX_UPLOAD_MB': '10',
            'ZENDILOHUB_AUDIT_RETENTION_DAYS': '90',
            'ZENDILOHUB_MULTI_TENANT': 'true',
        }
    )

    assert config.host == '127.0.0.1'
    assert config.port == 9000
    assert config.log_level == 'debug'
    assert config.database_url == 'postgresql://db/zendilohub'
    assert config.redis_url == 'redis://cache:6379/1'
    assert config.data_dir == Path('/data')
    assert config.web_dir == Path('/app/web')
    assert config.public_url == 'https://app.zendilohub.example'
    assert config.trusted_proxies == '10.0.0.1'
    assert config.api_docs is False
    assert config.max_upload_bytes == 10 * 1024 * 1024
    assert config.audit_retention_days == 90
    assert config.multi_tenant is True


@pytest.mark.parametrize('value', ['yes', 'TRUE', '1', 'on'])
def test_accepts_common_spellings_of_true(value: str) -> None:
    assert load_config({'ZENDILOHUB_API_DOCS': value}).api_docs is True


@pytest.mark.parametrize(
    ('name', 'value', 'message'),
    [
        ('ZENDILOHUB_PORT', '0', 'ZENDILOHUB_PORT must be a port number'),
        ('ZENDILOHUB_PORT', 'http', 'ZENDILOHUB_PORT must be a port number'),
        ('ZENDILOHUB_LOG_LEVEL', 'loud', 'ZENDILOHUB_LOG_LEVEL must be one of'),
        ('ZENDILOHUB_MAX_UPLOAD_MB', '0', 'ZENDILOHUB_MAX_UPLOAD_MB must be a whole number of at least 1'),
        ('ZENDILOHUB_API_DOCS', 'maybe', 'ZENDILOHUB_API_DOCS must be true or false'),
        ('ZENDILOHUB_PUBLIC_URL', 'app.zendilohub.example', 'ZENDILOHUB_PUBLIC_URL must start with http'),
        ('ZENDILOHUB_MULTI_TENANT', 'maybe', 'ZENDILOHUB_MULTI_TENANT must be true or false'),
    ],
)
def test_rejects_invalid_values(name: str, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_config({name: value})


def test_reads_the_initial_administrator() -> None:
    config = load_config(
        {'ZENDILOHUB_ADMIN_EMAIL': ' admin@example.org ', 'ZENDILOHUB_ADMIN_PASSWORD': ' hidden words '}
    )

    assert config.initial_admin == InitialAdmin(email='admin@example.org', password=' hidden words ')
    assert 'hidden words' not in repr(config)


@pytest.mark.parametrize(
    'env',
    [{'ZENDILOHUB_ADMIN_EMAIL': 'admin@example.org'}, {'ZENDILOHUB_ADMIN_PASSWORD': 'correct horse battery'}],
)
def test_wants_both_parts_of_the_initial_administrator(env: dict[str, str]) -> None:
    with pytest.raises(ValueError, match='set both or neither'):
        load_config(env)
