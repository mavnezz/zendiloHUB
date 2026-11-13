from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class MailMessage:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    async def send(self, message: MailMessage) -> None: ...
