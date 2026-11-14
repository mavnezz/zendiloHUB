from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import ExtendedKeyUsageOID

from support.smime import ENGINE, NOW, authority, encrypted_mail, entity, person, signed_mail
from zendilohub.core.domain.files import FileData
from zendilohub.modules.channels.domain.models import smime_mime
from zendilohub.modules.channels.domain.models.smime import (
    Certificate,
    Seal,
    Verification,
    choose,
    signature_status,
)
from zendilohub.modules.channels.domain.ports.services import MailboxError, OutgoingMail, SmimeError
from zendilohub.modules.channels.infrastructure.mail_servers import compose_sealed
from zendilohub.modules.channels.infrastructure.smime import BerError, CryptographySmime, oid, parse

CA = authority()
ALICE = person('alice@acme.example', CA)


def _status(raw: bytes, trusted: list[str], sender: str = 'alice@acme.example') -> str:
    layer = smime_mime.layer(raw)
    assert layer is not None
    verification = ENGINE.verify(layer.data, layer.content if layer.kind == 'signed' else None, trusted, NOW)
    return signature_status(verification, sender, NOW)


def test_signatures_are_checked() -> None:
    raw = signed_mail(ALICE, sender='alice@acme.example')
    assert _status(raw, [CA.pem]) == 'valid'
    assert _status(raw, []) == 'untrusted'
    assert _status(raw, [ALICE.pem]) == 'valid'
    assert _status(raw, [CA.pem], sender='mallory@acme.example') == 'untrusted'
    assert _status(raw.replace(b'does not print', b'prints fine!!'), [CA.pem]) == 'invalid'
    expired = person('alice@acme.example', CA, expired=True)
    assert _status(signed_mail(expired, sender='alice@acme.example'), [CA.pem]) == 'expired'
    server_only = person('alice@acme.example', CA, usage=ExtendedKeyUsageOID.SERVER_AUTH)
    assert _status(signed_mail(server_only, sender='alice@acme.example'), [CA.pem]) == 'untrusted'
    no_usage = person('alice@acme.example', CA, usage=None)
    assert _status(signed_mail(no_usage, sender='alice@acme.example'), [CA.pem]) == 'valid'
    ecdsa = person('alice@acme.example', CA, kind='ec')
    assert _status(signed_mail(ecdsa, sender='alice@acme.example'), [CA.pem]) == 'valid'
    # A chain: the authority certified an intermediate one, which certified Bob.
    intermediate = person('ca@acme.example', CA)
    assert _status(signed_mail(person('bob@acme.example', intermediate), sender='bob@acme.example'), [CA.pem]) == (
        'untrusted'
    )


def _sign(options: list[pkcs7.PKCS7Options], *, pss: bool = False, content: bytes = b'Hello') -> bytes:
    builder = pkcs7.PKCS7SignatureBuilder().set_data(content)
    builder = builder.add_signer(
        ALICE.certificate,
        ALICE.key,
        hashes.SHA256(),
        rsa_padding=padding.PSS(padding.MGF1(hashes.SHA256()), padding.PSS.DIGEST_LENGTH) if pss else None,
    )
    return builder.sign(serialization.Encoding.DER, options)


def test_signatures_in_other_forms() -> None:
    engine = CryptographySmime()
    opaque = engine.verify(_sign([pkcs7.PKCS7Options.Binary]), None, [CA.pem], NOW)
    assert (opaque.intact, opaque.trusted, opaque.content) == (True, True, b'Hello')
    detached = [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary]
    bare = _sign([*detached, pkcs7.PKCS7Options.NoAttributes])
    assert engine.verify(bare, b'Hello', [CA.pem], NOW).intact
    assert not engine.verify(bare, b'Hallo', [CA.pem], NOW).intact
    assert engine.verify(_sign(detached, pss=True), b'Hello', [CA.pem], NOW).intact
    # Without the signer's certificate inside, a known one is used; unknown: no signer.
    no_certs = _sign([*detached, pkcs7.PKCS7Options.NoCerts])
    assert engine.verify(no_certs, b'Hello', [ALICE.pem], NOW).intact
    assert engine.verify(no_certs, b'Hello', [], NOW) == Verification(intact=False, signer=None, trusted=False)
    broken = Verification(intact=False, signer=None, trusted=False)
    assert engine.verify(b'garbage', b'Hello', [], NOW) == broken
    assert engine.verify(engine.encrypt(b'x', [ALICE.pem]), b'Hello', [], NOW) == broken
    assert engine.kind(b'\x30\x03\x02\x01\x01') is None
    assert engine.kind(b'nonsense') is None


def test_encrypts_and_decrypts() -> None:
    data = ENGINE.encrypt(b'Secret', [ALICE.pem, ALICE.pem])
    assert ENGINE.kind(data) == 'enveloped'
    assert ENGINE.decrypt(data, ALICE.signing) == b'Secret'
    assert ENGINE.decrypt(data, person('bob@acme.example', CA).signing) is None
    assert ENGINE.decrypt(data, person('eve@acme.example', CA, kind='ec').signing) is None
    with pytest.raises(SmimeError, match='recipient_key'):
        ENGINE.encrypt(b'x', [person('eve@acme.example', CA, kind='ec').pem])


def test_reads_certificates_and_keys() -> None:
    info = ENGINE.read_certificate(ALICE.certificate.public_bytes(serialization.Encoding.DER))
    assert (info.emails, info.is_ca, info.subject) == (('alice@acme.example',), False, 'CN=alice@acme.example')
    assert ENGINE.read_certificate(CA.pem.encode()).is_ca
    with pytest.raises(SmimeError, match='certificate'):
        ENGINE.read_certificate(b'-----BEGIN CERTIFICATE-----\nnope\n-----END CERTIFICATE-----')
    certificate, key = ENGINE.read_pkcs12(ALICE.pkcs12('pw'), 'pw')
    assert certificate.fingerprint == info.fingerprint
    assert 'PRIVATE KEY' in key
    with pytest.raises(SmimeError, match='pkcs12'):
        ENGINE.read_pkcs12(ALICE.pkcs12('pw'), 'wrong')
    der_key = ALICE.key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    assert ENGINE.read_key(der_key, '', info) == ALICE.key_pem
    with pytest.raises(SmimeError, match=r'^key$'):
        ENGINE.read_key(b'nope', '', info)
    with pytest.raises(SmimeError, match='key_mismatch'):
        ENGINE.read_key(CA.key.private_bytes(*_pkcs8()), '', info)
    # Only the e-mail attribute of the subject names the address.
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.EMAIL_ADDRESS, 'Old@Style.example')]))
        .issuer_name(CA.certificate.subject)
        .public_key(ALICE.key.public_key())
        .serial_number(7)
        .not_valid_before(NOW - timedelta(days=1))
        .not_valid_after(NOW + timedelta(days=1))
    )
    old = builder.sign(CA.key, hashes.SHA256())
    assert ENGINE.read_certificate(old.public_bytes(serialization.Encoding.PEM)).emails == ('old@style.example',)


def _pkcs8() -> tuple[serialization.Encoding, serialization.PrivateFormat, serialization.NoEncryption]:
    return serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()


def test_reads_ber() -> None:
    node, end = parse(b'\x30\x80\x24\x80\x04\x01a\x04\x01b\x00\x00\x02\x01\x05\x00\x00')
    assert (end, node.constructed, len(node.children)) == (17, True, 2)
    assert node.children[0].octets() == b'ab'
    assert oid(parse(b'\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02')[0]) == '1.2.840.113549.1.7.2'
    long_tag, _ = parse(b'\x9f\x81\x01\x01x')
    assert (long_tag.number, long_tag.context, long_tag.value) == (129, True, b'x')
    long_length, _ = parse(b'\x04\x81\x01y')
    assert long_length.value == b'y'
    for broken in (b'\x04', b'\x04\x05ab', b'\x04\x80ab', b'\x04\x85\x00\x00\x00\x00\x01', b'\x1f\x81', b'\x1f\x01'):
        with pytest.raises(BerError):
            parse(broken)
    with pytest.raises(BerError):
        oid(parse(b'\x04\x01a')[0])


def test_mime_layers() -> None:
    assert smime_mime.layer(b'From: a@b\r\nSubject: x\r\n\r\nplain') is None
    assert smime_mime.layer(b'Content-Type: multipart/signed\r\n\r\nno boundary') is None
    assert smime_mime.layer(b'Content-Type: application/pkcs7-mime\r\n\r\n') is None
    assert smime_mime.split(b'only headers') == (b'only headers', b'')
    wrong_part = (
        b'Content-Type: multipart/signed; boundary="b"\r\n\r\n--b\r\nhello\r\n--b\r\n'
        b'Content-Type: text/plain\r\n\r\nnot a signature\r\n--b--\r\n'
    )
    assert smime_mime.layer(wrong_part) is None
    empty = wrong_part.replace(
        b'Content-Type: text/plain\r\n\r\nnot a signature', b'Content-Type: application/pkcs7-signature\r\n\r\n'
    )
    assert smime_mime.layer(empty) is None
    short = b'Content-Type: multipart/signed; boundary="b"\r\n\r\n--b\r\nhello\r\n--b--\r\n'
    assert smime_mime.layer(short) is None
    # Mails with bare line ends still check out: the content is made canonical.
    raw = signed_mail(ALICE, sender='alice@acme.example').replace(b'\r\n', b'\n')
    assert _status(raw, [CA.pem]) == 'valid'
    whole = smime_mime.with_headers(b'From: a@b\r\nContent-Type: text/html\r\nX-Long: a\r\n b', b'just text')
    assert (
        whole
        == b'From: a@b\r\nX-Long: a\r\n b\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset="utf-8"\r\n\r\njust text'
    )
    assert smime_mime.sender(encrypted_mail(ALICE, sender='Carl <Carl@Customer.example>')) == 'carl@customer.example'


def test_chooses_the_certificate_that_lasts() -> None:
    def certificate(identity_id: str, days: int) -> Certificate:
        info = ENGINE.read_certificate(ALICE.pem.encode())
        from dataclasses import replace

        return Certificate(
            id=identity_id,
            tenant_id='t',
            kind='contact',
            info=replace(info, not_after=NOW + timedelta(days=days)),
            private_key=None,
            created_at=NOW,
        )

    found = choose([certificate('a', 10), certificate('b', 30), certificate('c', -1)], 'Alice@acme.example ', NOW)
    assert found is not None
    assert found.id == 'b'
    assert choose([certificate('a', 10)], 'bob@acme.example', NOW) is None


def test_sealing_fails_cleanly() -> None:
    class Broken(CryptographySmime):
        def encrypt(self, content: bytes, recipients: object) -> bytes:
            raise SmimeError('recipient_key')

    mail = OutgoingMail(
        sender='alice@acme.example',
        to=('bob@acme.example',),
        subject='Hi',
        text='Hello',
        message_id='<x@acme.example>',
        attachments=(FileData(filename='a.txt', content_type='text/plain', content=b'file'),),
        seal=Seal(encrypt_for=(ALICE.pem,)),
    )
    with pytest.raises(MailboxError, match='recipient_key'):
        compose_sealed(mail, Broken())
    assert Seal().any is False
    assert entity('x').endswith(b'x\r\n')
