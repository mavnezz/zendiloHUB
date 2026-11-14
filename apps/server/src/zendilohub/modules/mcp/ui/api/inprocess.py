"""Calls the app's own API in-process, as an AI assistant (the HTTP policies see it in the ASGI scope)."""

import json
from typing import Any
from urllib.parse import urlencode

from starlette.types import ASGIApp, Message

from zendilohub.core.domain.assistant_access import AssistantAccess
from zendilohub.core.http.access import ASSISTANT_ACCESS


class ApiError(Exception):
    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f'{status}')
        self.status, self.body = status, body

    @property
    def message(self) -> str:
        if isinstance(self.body, dict):
            return str(self.body.get('message') or self.body.get('error') or self.status)
        return str(self.status)


class InProcessApi:
    def __init__(self, app: ASGIApp, access: AssistantAccess) -> None:
        self._app = app
        self._access = access

    @property
    def user_id(self) -> str:
        """The member the assistant acts for."""
        return self._access.user_id

    async def call(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        payload = json.dumps(body).encode() if body is not None else b''
        pairs = [(key, item) for key, value in (query or {}).items() if value is not None for item in _items(value)]
        scope: dict[str, Any] = {
            'type': 'http',
            'asgi': {'version': '3.0'},
            'http_version': '1.1',
            'method': method,
            'scheme': 'http',
            'path': f'/api/v1{path}',
            'raw_path': f'/api/v1{path}'.encode(),
            'query_string': urlencode(pairs).encode(),
            'headers': [(b'content-type', b'application/json'), (b'host', b'mcp.internal')],
            'client': ('127.0.0.1', 0),
            'server': ('mcp.internal', 80),
            ASSISTANT_ACCESS: self._access,
        }
        sent = False

        async def receive() -> Message:
            nonlocal sent
            if sent:
                return {'type': 'http.disconnect'}
            sent = True
            return {'type': 'http.request', 'body': payload, 'more_body': False}

        status = 500
        chunks: list[bytes] = []

        async def send(message: Message) -> None:
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            elif message['type'] == 'http.response.body':
                chunks.append(message.get('body', b''))

        await self._app(scope, receive, send)
        raw = b''.join(chunks)
        data = json.loads(raw) if raw else None
        if status >= 400:
            raise ApiError(status, data)
        return data


def _items(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(each) for each in value]
    if isinstance(value, bool):
        return ['true' if value else 'false']
    return [str(value)]
