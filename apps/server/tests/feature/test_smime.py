from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization

from support.app import AppUnderTest
from support.helpdesk import posted
from support.mail_desk import SUPPORT, fetch, mail_desk, tickets
from support.mail_server import email
from support.smime import ENGINE, NOW, authority, encrypted_mail, entity, person, signed_mail
from support.tenancy import member_of
from zendilohub.modules.channels.domain.models import smime_mime
from zendilohub.modules.channels.infrastructure.mail_servers import compose_sealed

CUSTOMER = 'carl@customer.example'


async def upload(
    client: httpx.AsyncClient,
    base: str,
    kind: str,
    data: bytes,
    *,
    password: str = '',
    key: bytes | None = None,
) -> httpx.Response:
    files: dict[str, Any] = {'file': ('cert', data)}
    if key is not None:
        files['key'] = ('key.pem', key)
    return await client.post(f'{base}/smime/certificates', data={'kind': kind, 'password': password}, files=files)


async def test_manages_certificates(app: AppUnderTest) -> None:
    ada, tenant, base, _support, _account = await mail_desk(app)
    ca = authority()
    own = person(SUPPORT, ca)

    wrong = await upload(ada, base, 'own', own.pkcs12('secret'), password='wrong')
    assert (wrong.json()['error'], wrong.json()['params']) == ('invalid_certificate', {'field': 'pkcs12'})
    added = await upload(ada, base, 'own', own.pkcs12('secret'), password='secret')
    assert added.status_code == 201, added.text
    body = added.json()
    assert (body['kind'], body['emails'], body['has_key']) == ('own', [SUPPORT], True)
    assert 'private_key' not in body
    assert 'PRIVATE' not in added.text
    assert (await upload(ada, base, 'own', own.pkcs12('x'), password='x')).json()['error'] == 'certificate_exists'

    # A certificate with its key in PEM; a key of another certificate does not fit.
    second = person('help@acme.example', ca)
    mismatch = await upload(ada, base, 'own', second.pem.encode(), key=own.key_pem.encode())
    assert mismatch.json()['params'] == {'field': 'key_mismatch'}
    protected = second.key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b'pw'),
    )
    assert (await upload(ada, base, 'own', second.pem.encode(), key=protected, password='pw')).status_code == 201

    contact = person(CUSTOMER, ca)
    der = contact.certificate.public_bytes(serialization.Encoding.DER)
    assert (await upload(ada, base, 'contact', der)).json()['emails'] == [CUSTOMER]
    assert (await upload(ada, base, 'ca', contact.pem.encode())).json()['params'] == {'field': 'not_ca'}
    assert (await upload(ada, base, 'ca', ca.pem.encode())).status_code == 201
    assert (await upload(ada, base, 'contact', b'nonsense')).json()['params'] == {'field': 'certificate'}
    expired = person('old@customer.example', ca, expired=True)
    assert (await upload(ada, base, 'contact', expired.pem.encode())).json()['params'] == {'field': 'expired'}
    nobody = authority('No mail')
    assert (await upload(ada, base, 'contact', nobody.pem.encode())).json()['params'] == {'field': 'no_email'}

    listed = (await ada.get(f'{base}/smime/certificates')).json()
    assert sorted(each['kind'] for each in listed) == ['ca', 'contact', 'own', 'own']
    contacts = (await ada.get(f'{base}/smime/certificates', params={'kind': 'contact'})).json()
    assert [each['has_key'] for each in contacts] == [False]
    path = f'{base}/smime/certificates/{contacts[0]["id"]}'
    assert (await ada.delete(path)).status_code == 204
    assert (await ada.delete(path)).json()['error'] == 'certificate_not_found'

    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(f'{base}/smime/certificates')).status_code == 403
    log = {entry['action'] for entry in (await ada.get(f'{base}/audit-log')).json()['items']}
    assert {'smime_certificate.added', 'smime_certificate.deleted'} <= log


async def _reply(app: AppUnderTest, ada: httpx.AsyncClient, base: str, text: str) -> dict[str, Any]:
    [ticket] = await tickets(ada, base)
    return await _reply_to(app, ada, base, ticket['id'], text)


async def test_signs_and_encrypts_replies(app: AppUnderTest) -> None:
    ada, _tenant, base, support, account = await mail_desk(app)
    ca = authority()
    own, customer = person(SUPPORT, ca), person(CUSTOMER, ca)
    app.mail.deliver(SUPPORT, email())
    await fetch(app)
    settings = {'account_id': account['id'], 'smime_sign': True, 'smime_encrypt': 'when_possible'}
    saved = (await ada.put(f'{base}/queue-channels/{support}', json=settings)).json()
    assert (saved['smime_sign'], saved['smime_encrypt']) == (True, 'when_possible')
    invalid = await ada.put(f'{base}/queue-channels/{support}', json={**settings, 'smime_encrypt': 'sometimes'})
    assert invalid.status_code == 422

    # Signing without an own certificate: not sent, a person has to add it.
    assert (await _reply(app, ada, base, 'Unsigned?'))['error'] == 'smime_no_key'
    await upload(ada, base, 'own', own.pkcs12(), password='secret')

    # Signed only: the customer's certificate is not known yet.
    assert (await _reply(app, ada, base, 'Signed.'))['status'] == 'sent'
    _, mail = app.mail.sent[-1]
    assert mail.seal is not None
    assert mail.seal.sign is not None
    assert mail.seal.encrypt_for == ()
    raw = compose_sealed(mail, ENGINE)
    layer = smime_mime.layer(raw)
    assert layer is not None
    assert layer.kind == 'signed'
    checked = ENGINE.verify(layer.data, layer.content, [ca.pem], NOW)
    assert (checked.intact, checked.trusted, checked.signer and checked.signer.emails) == (True, True, (SUPPORT,))

    # With the customer's certificate: signed, then encrypted for them and for us.
    await upload(ada, base, 'contact', customer.pem.encode())
    assert (await _reply(app, ada, base, 'Secret.'))['status'] == 'sent'
    _, mail = app.mail.sent[-1]
    assert mail.seal is not None
    assert set(mail.seal.encrypt_for) == {customer.pem, own.pem}
    raw = compose_sealed(mail, ENGINE)
    outer = smime_mime.layer(raw)
    assert outer is not None
    assert ENGINE.kind(outer.data) == 'enveloped'
    for reader in (customer, own):
        opened = ENGINE.decrypt(outer.data, reader.signing)
        assert opened is not None
        assert b'multipart/signed' in opened

    # Always encrypted: without the customer's certificate it does not go out.
    contact = (await ada.get(f'{base}/smime/certificates', params={'kind': 'contact'})).json()[0]
    await ada.delete(f'{base}/smime/certificates/{contact["id"]}')
    await ada.put(f'{base}/queue-channels/{support}', json={**settings, 'smime_encrypt': 'always'})
    failed = await _reply(app, ada, base, 'Never in clear.')
    assert (failed['status'], failed['error']) == ('failed', 'smime_no_certificate')


async def test_opens_signed_and_encrypted_mail(app: AppUnderTest) -> None:
    ada, _tenant, base, support, account = await mail_desk(app)
    ca, stranger = authority(), authority('Stranger CA')
    own, customer = person(SUPPORT, ca), person(CUSTOMER, ca)
    await upload(ada, base, 'own', own.pkcs12(), password='secret')
    await upload(ada, base, 'ca', ca.pem.encode())

    app.mail.deliver(SUPPORT, signed_mail(customer))
    app.mail.deliver(SUPPORT, signed_mail(person(CUSTOMER, stranger), message_id='<s2@c>', subject='Untrusted'))
    tampered = signed_mail(customer, message_id='<s3@c>', subject='Tampered').replace(b'does not', b'DOES NOT')
    app.mail.deliver(SUPPORT, tampered)
    app.mail.deliver(SUPPORT, encrypted_mail(own))
    app.mail.deliver(SUPPORT, encrypted_mail(person('someone@else.example', ca), message_id='<e2@c>'))
    await fetch(app)

    found = {each['subject']: each for each in await tickets(ada, base)}
    assert set(found) == {'Printer broken', 'Untrusted', 'Tampered', 'Secret'}

    async def first_message(subject: str) -> dict[str, Any]:
        messages = (await ada.get(f'{base}/tickets/{found[subject]["id"]}/messages')).json()
        return dict(messages[0])

    valid = await first_message('Printer broken')
    assert valid['security'] == {'signed': True, 'signature': 'valid', 'signer': CUSTOMER, 'encrypted': False}
    assert (valid['body'], valid['attachments']) == ('It does not print.', [])
    assert (await first_message('Untrusted'))['security']['signature'] == 'untrusted'
    assert (await first_message('Tampered'))['security']['signature'] == 'invalid'
    secret = await first_message('Secret')
    assert (secret['body'], secret['security']['encrypted'], secret['security']['signed']) == (
        'The code is 1234.',
        True,
        False,
    )

    # The trusted sender's certificate was collected (only that one), so replies to them can be encrypted.
    contacts = (await ada.get(f'{base}/smime/certificates', params={'kind': 'contact'})).json()
    assert [(each['emails'], each['issuer']) for each in contacts] == [([CUSTOMER], 'CN=Test CA')]
    await ada.put(f'{base}/queue-channels/{support}', json={'account_id': account['id'], 'smime_encrypt': 'always'})
    assert (await _reply_to(app, ada, base, found['Printer broken']['id'], 'Encrypted.'))['status'] == 'sent'

    # An encrypted mail for none of our keys waits in the failed e-mails.
    [failed] = (await ada.get(f'{base}/failed-emails')).json()
    assert 'smime_decrypt_failed' in failed['error']
    # Plain mails stay without a security summary.
    app.mail.deliver(SUPPORT, email(message_id='<plain@c>', subject='Plain'))
    await fetch(app)
    plain = {each['subject']: each for each in await tickets(ada, base)}['Plain']
    assert (await ada.get(f'{base}/tickets/{plain["id"]}/messages')).json()[0]['security'] is None
    assert entity()


async def _reply_to(app: AppUnderTest, ada: httpx.AsyncClient, base: str, ticket_id: str, text: str) -> dict[str, Any]:
    path = f'{base}/tickets/{ticket_id}'
    message = await posted(ada, f'{path}/messages', kind='public', body=text)
    await app.run_jobs()
    statuses = {each['message_id']: each for each in (await ada.get(f'{path}/deliveries')).json()}
    return dict(statuses[message['id']])


async def test_signed_auto_replies(app: AppUnderTest) -> None:
    ada, _tenant, base, support, account = await mail_desk(app)
    ca = authority()
    await ada.put(
        f'{base}/queue-channels/{support}',
        json={
            'account_id': account['id'],
            'auto_reply': True,
            'auto_reply_subject': 'Got it',
            'auto_reply_body': 'Thanks',
            'smime_sign': True,
        },
    )
    # Without the key the acknowledgement is left out, the ticket is still made.
    app.mail.deliver(SUPPORT, email())
    await fetch(app)
    assert len(await tickets(ada, base)) == 1
    assert app.mail.sent == []
    await upload(ada, base, 'own', person(SUPPORT, ca).pkcs12(), password='secret')
    app.mail.deliver(SUPPORT, email(message_id='<m2@c>', subject='Another'))
    await fetch(app)
    [(_, sent)] = app.mail.sent
    assert sent.automatic
    assert sent.seal is not None
    assert sent.seal.sign is not None
