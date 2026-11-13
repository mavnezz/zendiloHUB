import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .error_handler import error_body

# Pure ASGI middlewares: Starlette's BaseHTTPMiddleware buffers and breaks streaming (SSE, downloads).

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'Cross-Origin-Opener-Policy': 'same-origin',
}

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

logger = logging.getLogger('zendilohub.http')


class SecurityHeaders:
    """Adds the security headers, and the web app's content security policy to its HTML pages."""

    def __init__(self, app: ASGIApp, policy: Callable[[], str | None]) -> None:
        self._app = app
        self._policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return
        path: str = scope['path']

        async def send_with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                policy = self._policy()
                # The API docs (Swagger UI) bring their own inline scripts and stylesheets.
                is_html = headers.get('content-type', '').startswith('text/html')
                if policy and is_html and not path.startswith('/api/'):
                    headers['Content-Security-Policy'] = policy
            await send(message)

        await self._app(scope, receive, send_with_headers)


class CrossSiteRequestGuard:
    """
    Rejects state-changing API requests and WebSockets a browser opens from another site (CSRF, cross-site
    WebSocket hijacking). The session cookie is SameSite=Lax on top of this.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'websocket' and is_cross_site(Headers(scope=scope)):
            # A WebSocket carries the session cookie like any request: another site must not open one.
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if (
            scope['type'] == 'http'
            and scope['method'] in UNSAFE_METHODS
            and scope['path'].startswith('/api/')
            and is_cross_site(Headers(scope=scope))
        ):
            response = JSONResponse(
                error_body('cross_site_request', 'Cross-site requests are not allowed'), status_code=403
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


def is_cross_site(headers: Headers) -> bool:
    site = headers.get('sec-fetch-site')
    if site is not None:
        return site not in ('same-origin', 'none')
    origin = headers.get('origin')
    if origin is None:
        # Not a browser (curl, scripts): there is no ambient cookie to abuse.
        return False
    host = headers.get('x-forwarded-host') or headers.get('host')
    return urlsplit(origin).netloc != host


class RequestLog:
    """Logs every request at debug level."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or not logger.isEnabledFor(logging.DEBUG):
            await self._app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_and_remember(message: Message) -> None:
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self._app(scope, receive, send_and_remember)
        finally:
            logger.debug(
                'Request completed',
                extra={
                    'method': scope['method'],
                    'path': scope['path'],
                    'status': status,
                    'ms': round((time.perf_counter() - started) * 1000, 1),
                },
            )
