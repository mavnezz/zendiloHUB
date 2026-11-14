import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, Request

from zendilohub.core.http.access import Public
from zendilohub.core.http.audit import Unaudited
from zendilohub.core.http.files import file_response
from zendilohub.core.http.http_kernel import HttpKernel
from zendilohub.modules.channels.domain.models.email import parse_email
from zendilohub.modules.tickets.domain.models.attachment import clean_content_type, clean_filename
from zendilohub.modules.tickets.infrastructure.file_store import DiskFileStore

TENANT = '00000000-0000-7000-8000-000000000001'
FILE = '00000000-0000-7000-8000-000000000002'


@pytest.mark.parametrize(
    ('name', 'cleaned'),
    [
        ('report.pdf', 'report.pdf'),
        ('C:\\Users\\carl\\Desktop\\photo.jpg', 'photo.jpg'),
        ('../../etc/passwd', 'passwd'),
        ('a\r\nb\x00c.txt', 'a__b_c.txt'),
        ('  ..hidden.  ', 'hidden'),
        ('', 'file'),
        ('...', 'file'),
        ('x' * 300 + '.tar.gz', 'x' * 197 + '.gz'),
        ('y' * 300, 'y' * 199),
        ('Rechnung März.pdf', 'Rechnung März.pdf'),
    ],
)
def test_cleans_file_names(name: str, cleaned: str) -> None:
    assert clean_filename(name) == cleaned
    assert len(clean_filename(name)) <= 200


@pytest.mark.parametrize(
    ('value', 'cleaned'),
    [
        ('image/PNG', 'image/png'),
        ('text/plain; charset=utf-8', 'text/plain'),
        ('text/html\r\nX-Evil: 1', 'application/octet-stream'),
        ('nonsense', 'application/octet-stream'),
        (None, 'application/octet-stream'),
        ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', None),
    ],
)
def test_cleans_content_types(value: str | None, cleaned: str | None) -> None:
    assert clean_content_type(value) == (cleaned or value)


async def test_keeps_files_on_disk(tmp_path: Path) -> None:
    store = DiskFileStore(tmp_path / 'files')
    assert list(store.stored(datetime.now(UTC))) == []
    assert await store.get(TENANT, FILE) is None
    await store.put(TENANT, FILE, b'content')
    assert await store.get(TENANT, FILE) == b'content'
    # No half-written files are left next to it.
    assert [each.name for each in (tmp_path / 'files' / TENANT).iterdir()] == [FILE]

    (tmp_path / 'files' / 'stray.txt').write_text('x')
    (tmp_path / 'files' / TENANT / 'stray').write_text('x')
    assert list(store.stored(datetime(2000, 1, 1, tzinfo=UTC))) == []
    later = datetime.fromtimestamp(os.stat(tmp_path / 'files' / TENANT / FILE).st_mtime + 10, UTC)
    assert list(store.stored(later)) == [(TENANT, FILE)]

    await store.delete(TENANT, FILE)
    await store.delete(TENANT, FILE)
    assert await store.get(TENANT, FILE) is None
    for tenant, file in [('../x', FILE), (TENANT, '../../etc/passwd'), (TENANT, '')]:
        with pytest.raises(ValueError, match='UUIDs'):
            await store.put(tenant, file, b'')


async def test_leaves_nothing_behind_when_writing_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = DiskFileStore(tmp_path)

    def broken(_source: str, _target: Path) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(os, 'replace', broken)
    with pytest.raises(OSError, match='disk full'):
        await store.put(TENANT, FILE, b'content')
    assert list((tmp_path / TENANT).iterdir()) == []


def test_reads_the_files_of_e_mails() -> None:
    mail = EmailMessage()
    mail['From'] = 'carl@customer.example'
    mail['Subject'] = 'Files'
    mail.set_content('Text')
    mail.add_attachment(b'one', maintype='application', subtype='pdf', filename='one.pdf')
    mail.add_attachment(b'two', maintype='image', subtype='png', cid='<logo@x>')
    mail.add_attachment(b'three', maintype='application', subtype='x+weird')
    part = list(mail.iter_attachments())[-1]
    assert isinstance(part, EmailMessage)
    del part['Content-Disposition']
    part['Content-Disposition'] = 'attachment'
    parsed = parse_email(mail.as_bytes())
    assert [(each.filename, each.content_type, each.content, each.content_id) for each in parsed.files] == [
        ('one.pdf', 'application/pdf', b'one', None),
        ('image.png', 'image/png', b'two', '<logo@x>'),
        ('file', 'application/x+weird', b'three', None),
    ]
    assert parsed.text == 'Text'
    assert parse_email(b'From: a@b.example\r\nSubject: plain\r\n\r\nHello').files == ()


def test_downloads_are_harmless() -> None:
    shown = file_response(b'png', filename='Über "x".png', content_type='image/png')
    assert shown.headers['content-type'] == 'image/png'
    assert shown.headers['content-disposition'] == (
        'inline; filename="_ber _x_.png"; filename*=UTF-8\'\'%C3%9Cber%20%22x%22.png'
    )
    saved = file_response(b'<script>', filename='page.html', content_type='text/html')
    assert (saved.headers['content-type'], saved.headers['content-disposition'][:10]) == (
        'application/octet-stream',
        'attachment',
    )


async def test_refuses_bodies_above_the_limit() -> None:
    kernel = HttpKernel(api_docs=False, max_body_bytes=10)
    router = APIRouter(dependencies=[Public, Unaudited])

    @router.post('/echo')
    async def echo(request: Request) -> dict[str, int]:
        return {'size': len(await request.body())}

    kernel.routes(router)
    transport = httpx.ASGITransport(app=kernel.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        assert (await client.post('/api/v1/echo', content=b'0123456789')).json() == {'size': 10}
        announced = await client.post('/api/v1/echo', content=b'0123456789x')
        assert (announced.status_code, announced.json()['error']) == (413, 'request_too_large')

        async def chunks() -> AsyncIterator[bytes]:
            yield b'012345'
            yield b'6789x'

        streamed = await client.post('/api/v1/echo', content=chunks())
        assert (streamed.status_code, streamed.json()['error']) == (413, 'request_too_large')
