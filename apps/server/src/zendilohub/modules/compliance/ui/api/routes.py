from typing import Annotated

from fastapi import APIRouter, Query

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import CurrentAdmin, Member, member_with
from zendilohub.core.http.ids import Id

from ...application.queries.audit_log import ListAuditLog
from .schemas import AuditPageResponse

type Offset = Annotated[int, Query(ge=0)]
type Limit = Annotated[int, Query(ge=1, le=200)]


def audit_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(tags=['audit'])

    @router.get('/tenants/{tenant_id}/audit-log')
    async def tenant_log(
        member: Annotated[Member, member_with('audit.view')], offset: Offset = 0, limit: Limit = 50
    ) -> AuditPageResponse:
        """Who changed what in the organization, newest first."""
        return AuditPageResponse.of(
            await bus.query(ListAuditLog(tenant_id=member.tenant_id, offset=offset, limit=limit))
        )

    @router.get('/admin/audit-log')
    async def platform_log(
        _admin: CurrentAdmin, tenant_id: Id | None = None, offset: Offset = 0, limit: Limit = 50
    ) -> AuditPageResponse:
        """Every entry of the platform (or of one organization), newest first."""
        return AuditPageResponse.of(await bus.query(ListAuditLog(tenant_id=tenant_id, offset=offset, limit=limit)))

    return router
