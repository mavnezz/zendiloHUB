from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, kw_only=True)
class FetchResult:
    status: int
    content_type: str
    body: bytes
    """At most the fetcher's size limit."""


class FetchBlockedError(Exception):
    """The address is not on the public internet (SSRF protection) or not http(s)."""


class FetchFailedError(Exception):
    """Unreachable, too slow or too large."""


class PublicFetcher(Protocol):
    """HTTP requests to the public internet only, for what organizations configure (tools, webhooks)."""

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
        """
        `content` is a body sent as it is (e.g. signed bytes); `time_limit` (seconds) and `size_limit` (bytes) override
        the fetcher's defaults.
        """
        ...
