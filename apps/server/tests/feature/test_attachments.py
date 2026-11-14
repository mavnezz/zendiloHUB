import os
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any

import httpx

from support.app import AppUnderTest
from support.helpdesk import grant, posted, queue, ticket
from support.identity import logged_in
from support.mail_desk import SUPPORT, fetch, mail_desk, tickets
from support.portal import PORTAL, sign_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


async def upload(
    client: httpx.AsyncClient, base: str, ticket_id: str, name: str, content: bytes, kind: str = 'text/plain'
) -> httpx.Response:
    return await client.post(f'{base}/tickets/{ticket_id}/attachments', files={'file': (name, content, kind)})


async def uploaded(client: httpx.AsyncClient, base: str, ticket_id: str, name: str, content: bytes, **kw: Any) -> str:
    response = await upload(client, base, ticket_id, name, content, **kw)
    assert response.status_code == 201, response.text
    return str(response.json()['id'])


async def test_files_go_with_a_message(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    mine = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{mine["id"]}'

    response = await upload(ada, base, mine['id'], '../../etc/pass<wd>.txt', b'hello', 'text/plain; charset=utf-8')
    assert response.status_code == 201, response.text
    report = response.json()
    assert (report['filename'], report['content_type'], report['size'], report['inline']) == (
        'pass_wd_.txt',
        'text/plain',
        5,
        False,
    )
    image = await uploaded(ada, base, mine['id'], 'shot.png', PNG, kind='image/png')

    # Only the uploader sees a pending file.
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    await grant(ada, tenant, support, [await user_id_of(bob)], ['view', 'reply'])
    assert (await bob.get(f'{path}/attachments/{report["id"]}')).json()['error'] == 'attachment_not_found'
    taken = await bob.post(f'{path}/messages', json={'kind': 'public', 'body': 'x', 'attachment_ids': [image]})
    assert taken.json()['params'] == {'field': 'attachments'}

    # The text may be empty when files come along.
    message = await posted(
        ada, f'{path}/messages', kind='internal', body='', attachment_ids=[report['id'], image, report['id']]
    )
    assert [each['filename'] for each in message['attachments']] == ['pass_wd_.txt', 'shot.png']
    again = await ada.post(f'{path}/messages', json={'kind': 'internal', 'body': 'x', 'attachment_ids': [image]})
    assert again.json()['params'] == {'field': 'attachments'}
    assert (await ada.post(f'{path}/messages', json={'kind': 'internal', 'body': ' '})).json()['error'] == (
        'invalid_message'
    )
    listed = (await bob.get(f'{path}/messages')).json()
    assert [each['filename'] for each in listed[-1]['attachments']] == ['pass_wd_.txt', 'shot.png']

    download = await bob.get(f'{path}/attachments/{report["id"]}')
    assert download.content == b'hello'
    assert download.headers['content-type'] == 'application/octet-stream'
    assert download.headers['content-disposition'] == (
        'attachment; filename="pass_wd_.txt"; filename*=UTF-8\'\'pass_wd_.txt'
    )
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert 'sandbox' in download.headers['content-security-policy']
    shown = await bob.get(f'{path}/attachments/{image}')
    assert (shown.headers['content-type'], shown.headers['content-disposition'][:6]) == ('image/png', 'inline')

    # Taken files cannot be deleted; strangers and other tickets do not find them.
    assert (await ada.delete(f'{path}/attachments/{image}')).json()['error'] == 'attachment_not_found'
    other = await ticket(ada, tenant, support, 'Other')
    assert (await ada.get(f'{base}/tickets/{other["id"]}/attachments/{image}')).json()['error'] == (
        'attachment_not_found'
    )
    eve = await logged_in(app, 'eve@example.org')
    assert (await eve.get(f'{path}/attachments/{image}')).status_code in (403, 404)

    # Merging takes the files along.
    merged = await ada.post(f'{base}/tickets/{other["id"]}/merge', json={'number': mine['number']})
    assert merged.status_code == 200, merged.text
    assert (await ada.post(f'{path}/merge', json={'number': other['number']})).status_code in (200, 409)


async def test_uploads_need_rights_and_respect_the_limit(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    mine = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{mine["id"]}'

    cleo = await member_of(app, tenant, ada, 'cleo@example.org', 'agent')
    await grant(ada, tenant, support, [await user_id_of(cleo)], ['view'], name='Readers')
    refused = await upload(cleo, base, mine['id'], 'a.txt', b'a')
    assert refused.json()['error'] == 'queue_right_missing'

    limit = app.config.max_upload_bytes
    too_big = await upload(ada, base, mine['id'], 'big.bin', b'x' * (limit + 1))
    assert (too_big.status_code, too_big.json()['error'], too_big.json()['params']) == (
        413,
        'attachment_too_large',
        {'max_mb': limit // (1024 * 1024)},
    )
    huge = await ada.post(
        f'{path}/attachments', content=b'x' * (limit * 5 + 2 * 1024 * 1024), headers={'content-type': 'text/plain'}
    )
    assert (huge.status_code, huge.json()['error']) == (413, 'request_too_large')

    # Pending uploads can be taken back, and go by themselves after a day.
    first = await uploaded(ada, base, mine['id'], 'a.txt', b'a')
    assert (await ada.delete(f'{path}/attachments/{first}')).status_code == 204
    assert (await ada.get(f'{path}/attachments/{first}')).json()['error'] == 'attachment_not_found'
    second = await uploaded(ada, base, mine['id'], 'b.txt', b'b')
    store = app.config.data_dir / 'attachments' / tenant
    assert (store / second).read_bytes() == b'b'
    app.clock.advance(hours=25)
    await app.app.context.scheduler.run_all()
    assert not (store / second).exists()

    # Files whose ticket is gone are removed once they are old.
    third = await uploaded(ada, base, mine['id'], 'c.txt', b'c')
    await posted(ada, f'{path}/messages', kind='internal', body='with file', attachment_ids=[third])
    assert (await ada.delete(path)).status_code == 204
    old = app.clock.now().timestamp() - 3 * 24 * 3600
    os.utime(store / third, (old, old))
    (store / 'not-a-uuid').write_bytes(b'?')
    await app.app.context.scheduler.run_all()
    assert not (store / third).exists()
    assert (store / 'not-a-uuid').exists()


def with_files(*, text: str = 'See attached.', message_id: str = '<f1@customer.example>') -> bytes:
    mail = EmailMessage()
    mail['From'] = 'Carl Customer <carl@customer.example>'
    mail['To'] = SUPPORT
    mail['Subject'] = 'Invoice'
    mail['Date'] = formatdate()
    mail['Message-ID'] = message_id
    mail.set_content(text)
    mail.add_alternative('<p>See <img src="cid:logo@x"> attached.</p>', subtype='html')
    html = next(part for part in mail.iter_parts() if part.get_content_type() == 'text/html')
    assert isinstance(html, EmailMessage)
    html.add_related(PNG, maintype='image', subtype='png', cid='<logo@x>')
    mail.add_attachment(b'%PDF-1.7 invoice', maintype='application', subtype='pdf', filename='Rechnung März.pdf')
    mail.add_attachment(b'x' * (26 * 1024 * 1024), maintype='application', subtype='zip', filename='huge.zip')
    return mail.as_bytes()


async def test_files_of_e_mails_come_in_and_go_out(app: AppUnderTest) -> None:
    ada, _tenant, base, _support, _account = await mail_desk(app)
    app.mail.deliver(SUPPORT, with_files())
    await fetch(app)
    [created] = await tickets(ada, base)
    path = f'{base}/tickets/{created["id"]}'
    [received] = (await ada.get(f'{path}/messages')).json()
    files = received['attachments']
    # The huge one stays out: the upload limit holds for e-mails too.
    assert [(each['filename'], each['content_type']) for each in files] == [
        ('image.png', 'image/png'),
        ('Rechnung März.pdf', 'application/pdf'),
    ]
    pdf = await ada.get(f'{path}/attachments/{files[1]["id"]}')
    assert pdf.content == b'%PDF-1.7 invoice'
    assert "filename*=UTF-8''Rechnung%20M%C3%A4rz.pdf" in pdf.headers['content-disposition']

    sent_before = len(app.mail.sent)
    image = await uploaded(ada, base, created['id'], 'answer.png', PNG, kind='image/png')
    await posted(ada, f'{path}/messages', kind='public', body='Here you are.', attachment_ids=[image])
    await app.run_jobs()
    _address, reply = app.mail.sent[sent_before]
    assert [(each.filename, each.content_type, each.content) for each in reply.attachments] == [
        ('answer.png', 'image/png', PNG)
    ]

    # Only files: the message has no text.
    app.mail.deliver(SUPPORT, with_files(text='', message_id='<f2@customer.example>'))
    await fetch(app)
    assert len((await ada.get(f'{path}/messages')).json()) >= 2


async def test_customers_see_and_send_files_in_the_portal(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    mine = await ticket(ada, tenant, support, customer={'email': 'carl@acme.example', 'name': 'Carl'})
    path = f'{base}/tickets/{mine["id"]}'
    note = await uploaded(ada, base, mine['id'], 'secret.txt', b'internal')
    await posted(ada, f'{path}/messages', kind='internal', body='Note', attachment_ids=[note])
    shared = await uploaded(ada, base, mine['id'], 'manual.pdf', b'%PDF manual', kind='application/pdf')
    await posted(ada, f'{path}/messages', kind='public', body='The manual', attachment_ids=[shared])
    await ada.put(f'{base}/portal-settings', json={'enabled': True, 'queue_id': support})

    carl = await sign_in(app, tenant, 'carl@acme.example')
    portal = f'{PORTAL}/{tenant}/tickets/{mine["id"]}'
    thread = (await carl.get(portal)).json()
    assert [each['attachments'] for each in thread['messages']][-1] == [
        {'id': shared, 'filename': 'manual.pdf', 'content_type': 'application/pdf', 'size': 11}
    ]
    assert (await carl.get(f'{portal}/attachments/{shared}')).content == b'%PDF manual'
    assert (await carl.get(f'{portal}/attachments/{note}')).json()['error'] == 'ticket_not_found'
    pending = await uploaded(ada, base, mine['id'], 'draft.txt', b'draft')
    assert (await carl.get(f'{portal}/attachments/{pending}')).json()['error'] == 'ticket_not_found'
    assert (await app.client.get(f'{portal}/attachments/{shared}')).json()['error'] == 'portal_login_required'

    answered = await carl.post(
        f'{portal}/messages', data={'body': ''}, files=[('files', ('photo.png', PNG, 'image/png'))]
    )
    assert answered.status_code == 200, answered.text
    last = answered.json()['messages'][-1]
    assert (last['body'], [each['filename'] for each in last['attachments']]) == ('', ['photo.png'])
    assert (await carl.post(f'{portal}/messages', data={'body': ''})).json()['error'] == 'invalid_portal'
    many = [('files', (f'{n}.txt', b'n', 'text/plain')) for n in range(6)]
    assert (await carl.post(f'{portal}/messages', data={'body': 'x'}, files=many)).json()['params'] == {
        'field': 'files'
    }
    opened = await carl.post(
        f'{PORTAL}/{tenant}/tickets',
        data={'subject': 'Broken screen', 'body': 'See photo'},
        files=[('files', ('screen.jpg', b'\xff\xd8jpeg', 'image/jpeg'))],
    )
    assert opened.status_code == 201, opened.text
    seen = (await ada.get(f'{base}/tickets/{opened.json()["id"]}/messages')).json()
    assert [each['filename'] for each in seen[0]['attachments']] == ['screen.jpg']

    # At most 30 files an hour.
    for _ in range(5):
        five = [('files', (f'{n}.txt', b'n', 'text/plain')) for n in range(5)]
        await carl.post(f'{portal}/messages', data={'body': 'x'}, files=five)
    limited = await carl.post(
        f'{portal}/messages', data={'body': 'x'}, files=[('files', ('z.txt', b'z', 'text/plain'))] * 5
    )
    assert limited.json()['error'] == 'too_many_requests'
