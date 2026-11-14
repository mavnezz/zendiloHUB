from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.cipher import Cipher
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.exceptions import CertificateExistsError, CertificateNotFoundError, InvalidCertificateError
from ...domain.models.smime import CERTIFICATES_MAX, Certificate, CertificateKind
from ...domain.ports.repositories import CertificateRepository
from ...domain.ports.services import SmimeEngine, SmimeError
from ..services.smime import key_context


@dataclass(frozen=True, kw_only=True)
class AddCertificate(Command[Certificate]):
    """
    `own`: a PKCS #12 file with its password, or a certificate with its private key (`key`, PEM or DER, `password`
    if the key is protected). `contact` and `ca`: a certificate (PEM or DER).
    """

    tenant_id: str
    kind: CertificateKind
    data: bytes
    password: str = ''
    key: bytes | None = None


class AddCertificateHandler:
    def __init__(
        self,
        certificates: CertificateRepository,
        engine: SmimeEngine,
        cipher: Cipher,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._certificates = certificates
        self._engine = engine
        self._cipher = cipher
        self._ids = ids
        self._clock = clock

    async def handle(self, command: AddCertificate) -> Certificate:
        key: str | None
        try:
            if command.kind == 'own' and command.key is None:
                info, key = self._engine.read_pkcs12(command.data, command.password)
            else:
                info = self._engine.read_certificate(command.data)
                key = (
                    self._engine.read_key(command.key, command.password, info)
                    if command.kind == 'own' and command.key is not None
                    else None
                )
        except SmimeError as error:
            raise InvalidCertificateError(error.reason) from None
        now = self._clock.now()
        if info.not_after < now:
            raise InvalidCertificateError('expired')
        if command.kind == 'ca' and not info.is_ca:
            raise InvalidCertificateError('not_ca')
        if command.kind != 'ca' and not info.emails:
            raise InvalidCertificateError('no_email')
        if await self._certificates.count(command.tenant_id, command.kind) >= CERTIFICATES_MAX:
            raise InvalidCertificateError('limit')
        certificate = Certificate(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            kind=command.kind,
            info=info,
            private_key=None,
            created_at=now,
        )
        if key is not None:
            certificate.private_key = self._cipher.seal(key, context=key_context(certificate))
        if not await self._certificates.add(certificate):
            raise CertificateExistsError()
        return certificate


@dataclass(frozen=True, kw_only=True)
class DeleteCertificate(Command[None]):
    tenant_id: str
    certificate_id: str


class DeleteCertificateHandler:
    def __init__(self, certificates: CertificateRepository) -> None:
        self._certificates = certificates

    async def handle(self, command: DeleteCertificate) -> None:
        if await self._certificates.find(command.tenant_id, command.certificate_id) is None:
            raise CertificateNotFoundError()
        await self._certificates.delete(command.tenant_id, command.certificate_id)


@dataclass(frozen=True, kw_only=True)
class ListCertificates(Query[Sequence[Certificate]]):
    tenant_id: str
    kind: CertificateKind | None = None


class ListCertificatesHandler:
    def __init__(self, certificates: CertificateRepository) -> None:
        self._certificates = certificates

    async def handle(self, query: ListCertificates) -> Sequence[Certificate]:
        return await self._certificates.of_tenant(query.tenant_id, query.kind)
