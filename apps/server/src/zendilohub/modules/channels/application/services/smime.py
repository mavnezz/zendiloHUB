"""S/MIME for the organization's mail: which key signs, which certificates encrypt, and opening what comes in."""

import logging
from dataclasses import dataclass

from zendilohub.core.domain.cipher import Cipher
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.inbox import EmailSecurity

from ...domain.models import smime_mime
from ...domain.models.smime import (
    CERTIFICATES_MAX,
    Certificate,
    CertificateInfo,
    Seal,
    SigningKey,
    choose,
    signature_status,
)
from ...domain.ports.repositories import CertificateRepository, QueueChannelRepository
from ...domain.ports.services import SmimeEngine

logger = logging.getLogger(__name__)

LAYERS_MAX = 3
"""Signed, then encrypted, then signed again is as deep as mail programs go."""


class SealError(Exception):
    """The queue wants S/MIME, but it cannot be done: `smime_no_key` or `smime_no_certificate`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OpenError(Exception):
    """An encrypted mail none of the organization's keys opens."""


def key_context(certificate: Certificate) -> str:
    return f'smime:{certificate.tenant_id}:{certificate.id}'


@dataclass(frozen=True)
class Opened:
    raw: bytes
    """The mail with its S/MIME layers taken off (the headers stay)."""
    security: EmailSecurity | None


class Smime:
    def __init__(
        self,
        certificates: CertificateRepository,
        queues: QueueChannelRepository,
        engine: SmimeEngine,
        cipher: Cipher,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._certificates = certificates
        self._queues = queues
        self._engine = engine
        self._cipher = cipher
        self._ids = ids
        self._clock = clock

    def signing_key(self, certificate: Certificate) -> SigningKey | None:
        if certificate.private_key is None:
            return None
        key = self._cipher.open(certificate.private_key, context=key_context(certificate))
        return SigningKey(certificate.info.pem, key) if key else None

    async def seal(self, tenant_id: str, queue_id: str, sender: str, recipient: str) -> Seal | None:
        """How a mail of the queue from `sender` to `recipient` is protected; raises SealError."""
        settings = await self._queues.find(tenant_id, queue_id)
        if settings is None or (not settings.smime_sign and settings.smime_encrypt == 'never'):
            return None
        now = self._clock.now()
        own = choose(list(await self._certificates.for_address(tenant_id, 'own', sender)), sender, now)
        key = self.signing_key(own) if own else None
        if settings.smime_sign and key is None:
            raise SealError('smime_no_key')
        encrypt_for: tuple[str, ...] = ()
        if settings.smime_encrypt != 'never':
            contact = choose(
                list(await self._certificates.for_address(tenant_id, 'contact', recipient)), recipient, now
            )
            if contact is None and settings.smime_encrypt == 'always':
                raise SealError('smime_no_certificate')
            if contact is not None:
                # Also for our own certificate, so the copy in the sent folder stays readable.
                encrypt_for = (contact.info.pem, *([own.info.pem] if own else []))
        seal = Seal(sign=key if settings.smime_sign else None, encrypt_for=encrypt_for)
        return seal if seal.any else None

    async def open(self, tenant_id: str, raw: bytes) -> Opened:
        """Decrypts and checks signatures; raises OpenError if the mail is encrypted for none of our keys."""
        from_address = smime_mime.sender(raw)
        signed, encrypted = False, False
        status = None
        signer: str | None = None
        for _ in range(LAYERS_MAX):
            found = smime_mime.layer(raw)
            if found is None:
                break
            if found.kind == 'pkcs7' and self._engine.kind(found.data) == 'enveloped':
                inner = await self._decrypt(tenant_id, found.data)
                if inner is None:
                    raise OpenError('smime_decrypt_failed')
                raw, encrypted = smime_mime.replace_content(raw, inner), True
                continue
            if found.kind == 'pkcs7' and self._engine.kind(found.data) != 'signed':
                break
            # Authorities, and certificates the organization added or collected from trusted senders.
            trusted = [each.info.pem for each in await self._certificates.of_tenant(tenant_id)]
            now = self._clock.now()
            verification = self._engine.verify(
                found.data, found.content if found.kind == 'signed' else None, trusted, now
            )
            if not signed:
                # The outermost signature counts; inner ones are only unwrapped.
                signed = True
                status = signature_status(verification, from_address, now)
                signer = verification.signer.emails[0] if verification.signer and verification.signer.emails else None
                if status == 'valid' and verification.signer is not None:
                    await self._collect(tenant_id, verification.signer)
            content = found.content if found.kind == 'signed' else verification.content
            if content is None:
                break
            raw = smime_mime.replace_content(raw, content)
        if not signed and not encrypted:
            return Opened(raw, None)
        return Opened(raw, EmailSecurity(signed=signed, signature=status, signer=signer, encrypted=encrypted))

    async def _decrypt(self, tenant_id: str, data: bytes) -> bytes | None:
        for certificate in await self._certificates.of_tenant(tenant_id, 'own'):
            key = self.signing_key(certificate)
            if key is None:
                continue
            opened = self._engine.decrypt(data, key)
            if opened is not None:
                return opened
        return None

    async def _collect(self, tenant_id: str, info: CertificateInfo) -> None:
        """A trusted sender's certificate: from now on replies to them can be encrypted."""
        if await self._certificates.count(tenant_id, 'contact') >= CERTIFICATES_MAX:
            return
        added = await self._certificates.add(
            Certificate(
                id=self._ids.new_id(),
                tenant_id=tenant_id,
                kind='contact',
                info=info,
                private_key=None,
                created_at=self._clock.now(),
            )
        )
        if added:
            logger.info('Collected an S/MIME certificate', extra={'tenant': tenant_id, 'emails': list(info.emails)})
