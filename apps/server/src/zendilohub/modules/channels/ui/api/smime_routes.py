from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.audit import audited, note_audit
from zendilohub.core.http.files import read_upload
from zendilohub.core.http.ids import Id

from ...application.commands.smime import AddCertificate, DeleteCertificate, ListCertificates
from ...domain.models.smime import Certificate, CertificateKind
from .routes import Admin

FILE_MAX = 256 * 1024
"""Certificates and keys are a few kilobytes; PKCS #12 files with a chain stay well below this."""


class CertificateResponse(BaseModel):
    id: str
    kind: Literal['own', 'contact', 'ca']
    subject: str
    issuer: str
    serial: str
    emails: list[str]
    not_before: datetime
    not_after: datetime
    fingerprint: str
    """SHA-256, hex."""
    has_key: bool
    """Own certificates: the private key is stored (it is never shown)."""
    created_at: datetime

    @classmethod
    def of(cls, certificate: Certificate) -> CertificateResponse:
        info = certificate.info
        return cls(
            id=certificate.id,
            kind=certificate.kind,
            subject=info.subject,
            issuer=info.issuer,
            serial=info.serial,
            emails=list(info.emails),
            not_before=info.not_before,
            not_after=info.not_after,
            fingerprint=info.fingerprint,
            has_key=certificate.private_key is not None,
            created_at=certificate.created_at,
        )


def smime_routes(bus: CommandBus) -> APIRouter:
    """S/MIME certificates: own ones with their keys, contacts' and trusted authorities."""
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['channels'])

    @router.get('/smime/certificates')
    async def certificates(
        member: Admin, kind: Annotated[CertificateKind | None, Query()] = None
    ) -> list[CertificateResponse]:
        found = await bus.query(ListCertificates(tenant_id=member.tenant_id, kind=kind))
        return [CertificateResponse.of(each) for each in found]

    @router.post('/smime/certificates', status_code=201, dependencies=[audited('smime_certificate.added')])
    async def add(
        request: Request,
        member: Admin,
        kind: Annotated[CertificateKind, Form()],
        file: Annotated[UploadFile, File()],
        password: Annotated[str, Form(max_length=1000)] = '',
        key: Annotated[UploadFile | None, File()] = None,
    ) -> CertificateResponse:
        """
        `own`: a PKCS #12 file (.p12, .pfx) with its `password`, or a certificate with its private `key`.
        `contact`, `ca`: a certificate (PEM or DER).
        """
        data = (await read_upload(file, FILE_MAX)).content
        key_data = (await read_upload(key, FILE_MAX)).content if key is not None else None
        added = await bus.execute(
            AddCertificate(tenant_id=member.tenant_id, kind=kind, data=data, password=password, key=key_data)
        )
        note_audit(request, target=added.info.emails[0] if added.info.emails else added.info.subject[:200])
        return CertificateResponse.of(added)

    @router.delete(
        '/smime/certificates/{certificate_id}',
        status_code=204,
        response_class=Response,
        dependencies=[audited('smime_certificate.deleted')],
    )
    async def delete(certificate_id: Id, request: Request, member: Admin) -> None:
        await bus.execute(DeleteCertificate(tenant_id=member.tenant_id, certificate_id=certificate_id))
        note_audit(request, target=certificate_id)

    return router
