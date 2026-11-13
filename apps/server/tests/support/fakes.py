import json as json_module
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from zendilohub.core.domain.http_fetch import FetchResult
from zendilohub.core.domain.mailer import MailMessage
from zendilohub.core.infrastructure.public_fetcher import AiohttpPublicFetcher


class FakeClock:
    """A clock that only moves when a test says so."""

    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


class SequenceIds:
    """Predictable UUIDs: 00000000-0000-7000-8000-000000000001, …002, …"""

    def __init__(self) -> None:
        self.count = 0

    def new_id(self) -> str:
        self.count += 1
        return f'00000000-0000-7000-8000-{self.count:012d}'


class MemoryOutput:
    """Collects what a CLI command prints."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.errors: list[str] = []

    def line(self, text: str) -> None:
        self.lines.append(text)

    def error(self, text: str) -> None:
        self.errors.append(text)


class MemoryMailer:
    """Keeps the e-mails the app sends."""

    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.sent.append(message)

    def to(self, address: str) -> list[MailMessage]:
        return [message for message in self.sent if message.to == address]

    def last_link(self, address: str) -> str:
        """The URL in the newest e-mail to the address."""
        match = re.search(r'https?://\S+', self.to(address)[-1].text)
        assert match, f'No link in the e-mail to {address}'
        return match.group(0)

    def last_token(self, address: str) -> str:
        return self.last_link(address).split('token=')[1]


class MemoryJobs:
    """Remembers the enqueued jobs; a test runs them with `app.run_jobs` (the delayed ones with `run_delayed`)."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple[str, ...]]] = []
        self.delayed: list[tuple[str, tuple[str, ...], float]] = []

    async def enqueue(self, task: str, *args: str, delay: float = 0) -> None:
        if delay > 0:
            self.delayed.append((task, args, delay))
        else:
            self.enqueued.append((task, args))


class FakeWebsites:
    """
    The public internet for tests: answers for the addresses a test sets up, records what was sent there; every other
    address goes to the real fetcher (which refuses our own network).
    """

    def __init__(self) -> None:
        self.real = AiohttpPublicFetcher()
        self.answers: dict[str, FetchResult | Exception] = {}
        self.requests: list[SentRequest] = []

    def answer(self, url: str, status: int = 200, body: bytes = b'', content_type: str = 'text/plain') -> None:
        self.answers[url] = FetchResult(status=status, content_type=content_type, body=body)

    def fail(self, url: str, error: Exception) -> None:
        self.answers[url] = error

    def to(self, url: str) -> list[SentRequest]:
        return [request for request in self.requests if request.url == url]

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
        answer = self.answers.get(url)
        if answer is None:
            return await self.real.fetch(
                method, url, query=query, json=json, content=content, headers=headers, time_limit=time_limit
            )
        body = content if content is not None else (json_module.dumps(json).encode() if json is not None else b'')
        self.requests.append(SentRequest(method, url, body, dict(headers or {})))
        if isinstance(answer, Exception):
            raise answer
        return answer


@dataclass(frozen=True)
class SentRequest:
    method: str
    url: str
    body: bytes
    headers: dict[str, str]
