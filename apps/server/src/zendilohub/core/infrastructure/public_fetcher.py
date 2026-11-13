"""
HTTP requests to addresses organizations configure, which must never reach into our own network (SSRF): every
address a host name resolves to must be public; no redirects; a time and a size limit.
"""

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver

from ..domain.http_fetch import FetchBlockedError, FetchFailedError, FetchResult

USER_AGENT = 'zendiloHUB'


def is_public(address: str) -> bool:
    return ipaddress.ip_address(address).is_global


class NotPublicError(OSError):
    """A host name resolves to an address in a private or local network."""


class PublicResolver(AbstractResolver):
    """Resolves like the default resolver, then refuses hosts with any address that is not public."""

    def __init__(self) -> None:
        self._resolver = DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await self._resolver.resolve(host, port, family)
        if not results or not all(is_public(result['host']) for result in results):
            raise NotPublicError(f'{host} is not a public address')
        return results

    async def close(self) -> None:
        await self._resolver.close()


class AiohttpPublicFetcher:
    def __init__(self, *, timeout: float = 5, max_bytes: int = 64 * 1024) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_bytes = max_bytes

    async def fetch(
        self,
        method: str,
        url: str,
        *,
        query: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        time_limit: float | None = None,
        size_limit: int | None = None,
    ) -> FetchResult:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise FetchBlockedError(f'Not an http(s) address: {url}')
        try:
            if not is_public(parts.hostname):
                raise FetchBlockedError(f'{parts.hostname} is not a public address')
        except ValueError:
            pass  # A host name: the resolver checks what it resolves to.
        connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False)
        limit = aiohttp.ClientTimeout(total=time_limit) if time_limit else self._timeout
        try:
            async with (
                aiohttp.ClientSession(connector=connector, timeout=limit) as session,
                session.request(
                    method,
                    url,
                    params=query,
                    json=json,
                    data=content,
                    allow_redirects=False,
                    headers={
                        'Accept': 'application/json, text/plain;q=0.9, */*;q=0.1',
                        **(headers or {}),
                        'User-Agent': USER_AGENT,
                    },
                ) as response,
            ):
                most = size_limit or self._max_bytes
                body = b''
                while len(body) <= most:
                    # A read gives what has arrived so far, not all of it.
                    part = await response.content.read(most + 1 - len(body))
                    if not part:
                        break
                    body += part
                if len(body) > most:
                    raise FetchFailedError(f'The answer is larger than {most} bytes')
                return FetchResult(status=response.status, content_type=response.content_type, body=body)
        except aiohttp.ClientConnectorError as error:
            if isinstance(error.os_error, NotPublicError) or isinstance(error.__cause__, NotPublicError):
                raise FetchBlockedError(str(error.os_error)) from error
            raise FetchFailedError(str(error)) from error
        except (aiohttp.ClientError, TimeoutError) as error:
            raise FetchFailedError(str(error) or type(error).__name__) from error
