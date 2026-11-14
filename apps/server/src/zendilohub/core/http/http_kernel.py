import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.dependencies.models import Dependant
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from zendilohub.core.domain.permissions import MemberRole
from zendilohub.core.events.integration_events import ActionPerformed

from .access import (
    ACCESS_POLICIES,
    ApiKeyAccess,
    ApiKeyGuard,
    AuthGuard,
    MembershipGuard,
    Principal,
    require_person,
)
from .audit import AuditRecorder, AuditSink, declares_audit
from .content_security_policy import content_security_policy
from .error_handler import error_body, install_error_handlers
from .middleware import BodyLimit, CrossSiteRequestGuard, RequestLog, SecurityHeaders
from .public_api import public_operations, public_schema

API_PREFIX = '/api/v1'

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

logger = logging.getLogger(__name__)

type HealthCheck = Callable[[], Awaitable[bool]]


class HttpKernel:
    """
    Owns the FastAPI app: error format, security headers, CSRF guard, health check
    and serving the web app. Modules only add routers.
    """

    def __init__(
        self,
        *,
        api_docs: bool = True,
        version: str = '0.1.0',
        secret: Callable[[], bytes] = lambda: b'',
        max_body_bytes: int = 200 * 1024 * 1024,
    ) -> None:
        self.app = FastAPI(
            title='zendiloHUB API',
            version=version,
            docs_url='/api/docs' if api_docs else None,
            redoc_url=None,
            openapi_url='/api/openapi.json' if api_docs else None,
        )
        self.app.state.kernel = self
        self.secret = secret
        """The app's secret key, for keyed hashes."""
        self._guard: AuthGuard | None = None
        self._memberships: MembershipGuard | None = None
        self._api_keys: ApiKeyGuard | None = None
        self._audit_sink: AuditSink | None = None
        self._health_checks: dict[str, HealthCheck] = {}
        self._public_operations: set[tuple[str, str]] = set()
        self._policy: str | None = None

        install_error_handlers(self.app)
        # The last one added runs first.
        self.app.add_middleware(AuditRecorder, kernel=lambda: self)
        self.app.add_middleware(CrossSiteRequestGuard)
        self.app.add_middleware(SecurityHeaders, policy=lambda: self._policy)
        self.app.add_middleware(BodyLimit, max_bytes=lambda: max_body_bytes)
        self.app.add_middleware(RequestLog)

        for path in ('/health', f'{API_PREFIX}/health'):
            self.app.add_api_route(path, self._health, methods=['GET'], tags=['health'], include_in_schema=False)
        # The public API's reference (only what API keys can use), also when the full docs are off.
        self.app.add_api_route(
            '/api/reference/openapi.json', self._public_schema, methods=['GET'], include_in_schema=False
        )
        self.app.add_api_route('/api/reference', self._reference, methods=['GET'], include_in_schema=False)

    def use_auth_guard(self, guard: AuthGuard) -> None:
        self._guard = guard

    async def authenticate(self, session_token: str) -> Principal | None:
        return await self._guard.authenticate(session_token) if self._guard else None

    def use_api_key_guard(self, guard: ApiKeyGuard) -> None:
        self._api_keys = guard

    async def authenticate_key(self, token: str) -> ApiKeyAccess | None:
        return await self._api_keys.authenticate_key(token) if self._api_keys else None

    def use_membership_guard(self, guard: MembershipGuard) -> None:
        self._memberships = guard

    async def role_in(self, tenant_id: str, user_id: str) -> MemberRole | None:
        return await self._memberships.role_in(tenant_id, user_id) if self._memberships else None

    def use_audit_sink(self, sink: AuditSink) -> None:
        self._audit_sink = sink

    async def record(self, action: ActionPerformed) -> None:
        """Hands an audited request to the audit log; a failure there must not break the answer, but is logged."""
        if self._audit_sink is None:
            return
        try:
            await self._audit_sink(action)
        except Exception:
            logger.exception('Recording an audited action failed', extra={'action': action.action})

    def add_health_check(self, name: str, check: HealthCheck) -> None:
        self._health_checks[name] = check

    def routes(self, router: APIRouter) -> None:
        """Adds a module's routes below /api/v1. Every route must declare an access policy."""
        _check(router)
        self._public_operations |= public_operations(router.routes, API_PREFIX, require_person)
        self.app.include_router(router, prefix=API_PREFIX)

    def root_routes(self, router: APIRouter) -> None:
        """Adds routes whose paths a protocol fixes (OAuth's /.well-known/…, MCP), with the same checks."""
        _check(router)
        self.app.include_router(router)

    def serve_web_app(self, web_dir: Path) -> bool:
        """Serves the built SPA; unknown paths outside the API render index.html. False if there is no build."""
        index = web_dir / 'index.html'
        if not index.is_file():
            return False
        html = index.read_text('utf-8')
        self._policy = content_security_policy(html)
        if (web_dir / 'assets').is_dir():
            self.app.mount('/assets', _ImmutableFiles(directory=web_dir / 'assets'), name='assets')
        root = web_dir.resolve()

        async def spa(request: Request, path: str) -> Response:
            # Discovery documents a protocol asks for and zendiloHUB does not have are missing, not the web app.
            if request.method not in ('GET', 'HEAD') or path == 'api' or path.startswith(('api/', '.well-known/')):
                return JSONResponse(error_body('not_found', 'Route not found'), status_code=404)
            file = (root / path).resolve()
            if path and file.is_file() and file.is_relative_to(root) and file != index.resolve():
                return FileResponse(file, headers={'Cache-Control': 'no-cache'})
            return HTMLResponse(html, headers={'Cache-Control': 'no-cache'})

        self.app.add_api_route(
            '/{path:path}',
            spa,
            methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'],
            include_in_schema=False,
        )
        return True

    async def _public_schema(self) -> JSONResponse:
        return JSONResponse(public_schema(self.app.openapi(), self._public_operations))

    async def _reference(self) -> HTMLResponse:
        return get_redoc_html(openapi_url='/api/reference/openapi.json', title='zendiloHUB API')

    async def _health(self) -> JSONResponse:
        checks = {name: await check() for name, check in self._health_checks.items()}
        healthy = all(checks.values())
        body: dict[str, Any] = {
            'status': 'ok' if healthy else 'unavailable',
            'checks': {name: 'ok' if ok else 'down' for name, ok in checks.items()},
        }
        return JSONResponse(body, status_code=200 if healthy else 503)


def _check(router: APIRouter) -> None:
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = ','.join(sorted(route.methods or ()))
        if not _declares_policy(route.dependant):
            raise ValueError(f'Route {methods} {route.path} declares no access policy')
        if set(route.methods or ()) & UNSAFE_METHODS and not _declares_audit(route.dependant):
            raise ValueError(f'Route {methods} {route.path} declares no audit action (or Unaudited)')


def _declares_audit(dependant: Dependant) -> bool:
    return any(declares_audit(dependency.call) or _declares_audit(dependency) for dependency in dependant.dependencies)


def _declares_policy(dependant: Dependant) -> bool:
    return any(
        dependency.call in ACCESS_POLICIES or _declares_policy(dependency) for dependency in dependant.dependencies
    )


class _ImmutableFiles(StaticFiles):
    """Vite fingerprints everything in /assets, so those files never change."""

    def file_response(self, full_path: Any, stat_result: Any, scope: Scope, status_code: int = 200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response
