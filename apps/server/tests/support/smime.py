"""Certificates for S/MIME tests, made on the fly: an authority and people it certified."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from zendilohub.modules.channels.domain.models import smime_mime
from zendilohub.modules.channels.domain.models.smime import SigningKey
from zendilohub.modules.channels.infrastructure.smime import CryptographySmime

ENGINE = CryptographySmime()

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
"""The clock of the app in tests."""
START, END = datetime(2020, 1, 1, tzinfo=UTC), datetime(2036, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Identity:
    certificate: x509.Certificate
    key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey

    @property
    def pem(self) -> str:
        return self.certificate.public_bytes(serialization.Encoding.PEM).decode()

    @property
    def key_pem(self) -> str:
        return self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()

    @property
    def signing(self) -> SigningKey:
        return SigningKey(self.pem, self.key_pem)

    def pkcs12(self, password: str = 'secret') -> bytes:
        return pkcs12.serialize_key_and_certificates(
            b'test',
            self.key,
            self.certificate,
            None,
            serialization.BestAvailableEncryption(password.encode()),
        )


def _key(kind: str) -> rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1()) if kind == 'ec' else rsa.generate_private_key(65537, 2048)


def authority(name: str = 'Test CA') -> Identity:
    key = _key('rsa')
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(START)
        .not_valid_after(END)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return Identity(certificate, key)


def person(
    address: str,
    issuer: Identity | None = None,
    *,
    kind: str = 'rsa',
    expired: bool = False,
    usage: x509.ObjectIdentifier | None = ExtendedKeyUsageOID.EMAIL_PROTECTION,
) -> Identity:
    key = _key(kind)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)])
    start, end = (
        (NOW - timedelta(days=30), NOW - timedelta(days=1))
        if expired
        else (NOW - timedelta(days=1), NOW + timedelta(days=365))
    )
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer.certificate.subject if issuer else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.SubjectAlternativeName([x509.RFC822Name(address)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if usage is not None:
        builder = builder.add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
    certificate = builder.sign(issuer.key if issuer else key, hashes.SHA256())
    return Identity(certificate, key)


def entity(text: str = 'It does not print.') -> bytes:
    return smime_mime.canonical(f'Content-Type: text/plain; charset="utf-8"\n\n{text}\n'.encode())


def _headers(sender: str, to: str, subject: str, message_id: str) -> bytes:
    return (
        f'From: {sender}\r\nTo: {to}\r\nSubject: {subject}\r\nMessage-ID: {message_id}\r\n'
        'Date: Thu, 22 Oct 2026 12:00:00 +0000'
    ).encode()


def signed_mail(
    signer: Identity,
    *,
    sender: str = 'carl@customer.example',
    to: str = 'support@acme.example',
    subject: str = 'Printer broken',
    message_id: str = '<s1@customer.example>',
    content: bytes | None = None,
) -> bytes:
    content = content or entity()
    signature = ENGINE.sign(content, signer.signing)
    return smime_mime.with_headers(
        _headers(sender, to, subject, message_id), smime_mime.signed_entity(content, signature)
    )


def encrypted_mail(
    recipient: Identity,
    *,
    sender: str = 'carl@customer.example',
    to: str = 'support@acme.example',
    subject: str = 'Secret',
    message_id: str = '<e1@customer.example>',
    content: bytes | None = None,
) -> bytes:
    data = ENGINE.encrypt(content or entity('The code is 1234.'), [recipient.pem])
    return smime_mime.with_headers(_headers(sender, to, subject, message_id), smime_mime.enveloped_entity(data))
