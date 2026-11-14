"""S/MIME: certificates of the organization, its contacts and the authorities it trusts, and the queue's choice."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from zendilohub.core.domain.inbox import SignatureStatus

type CertificateKind = Literal['own', 'contact', 'ca']
"""`own`: a certificate with its private key, to sign and to decrypt; `contact`: a customer's, to encrypt to them;
`ca`: an authority whose certificates count as trusted when a signature is checked."""
CERTIFICATE_KINDS: tuple[CertificateKind, ...] = get_args(CertificateKind.__value__)

type EncryptMode = Literal['never', 'when_possible', 'always']
"""`when_possible`: encrypted if the recipient's certificate is known; `always`: not sent without it."""
ENCRYPT_MODES: tuple[EncryptMode, ...] = get_args(EncryptMode.__value__)

CERTIFICATES_MAX = 500
"""Per organization and kind; contact certificates collected from e-mails count too."""


@dataclass(frozen=True, kw_only=True)
class CertificateInfo:
    """What a certificate says about itself (read by the S/MIME engine)."""

    fingerprint: str
    """SHA-256 of the DER, hex."""
    subject: str
    issuer: str
    serial: str
    emails: tuple[str, ...]
    """Lower-case addresses from the subject alternative name and the subject's e-mail attribute."""
    not_before: datetime
    not_after: datetime
    pem: str
    is_ca: bool = False


@dataclass(kw_only=True)
class Certificate:
    id: str
    tenant_id: str
    kind: CertificateKind
    info: CertificateInfo
    private_key: bytes | None
    """Own certificates only: the private key (PEM, PKCS#8), sealed with the app's key."""
    created_at: datetime

    def covers(self, address: str) -> bool:
        return address.strip().lower() in self.info.emails

    def valid_at(self, now: datetime) -> bool:
        return self.info.not_before <= now <= self.info.not_after


@dataclass(frozen=True)
class SigningKey:
    certificate: str
    """PEM."""
    private_key: str
    """PEM, unsealed (only in memory while a mail is sealed or opened)."""


@dataclass(frozen=True, kw_only=True)
class Seal:
    """How an outgoing mail is protected: signed with `sign`, encrypted for `encrypt_for` (PEM certificates)."""

    sign: SigningKey | None = None
    encrypt_for: tuple[str, ...] = ()

    @property
    def any(self) -> bool:
        return self.sign is not None or bool(self.encrypt_for)


def choose(certificates: list[Certificate], address: str, now: datetime) -> Certificate | None:
    """The certificate for an address that is valid now and lasts longest."""
    usable = [each for each in certificates if each.covers(address) and each.valid_at(now)]
    return max(usable, key=lambda each: each.info.not_after, default=None)


@dataclass(frozen=True, kw_only=True)
class Verification:
    """What checking a signature found (the S/MIME engine's answer)."""

    intact: bool
    """The signature matches the content and the signer's key."""
    signer: CertificateInfo | None
    trusted: bool
    """The signer's certificate leads to a trusted one (a trusted authority or a certificate the organization added)
    and may protect e-mail."""
    content: bytes | None = None
    """The signed content, when it was inside the signature (opaque signing)."""


def signature_status(verification: Verification, from_address: str, now: datetime) -> SignatureStatus:
    signer = verification.signer
    if not verification.intact or signer is None:
        return 'invalid'
    if not signer.not_before <= now <= signer.not_after:
        return 'expired'
    if not verification.trusted or from_address.strip().lower() not in signer.emails:
        return 'untrusted'
    return 'valid'
