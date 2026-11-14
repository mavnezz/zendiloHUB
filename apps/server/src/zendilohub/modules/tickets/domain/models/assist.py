from dataclasses import dataclass
from typing import Literal

type AssistTask = Literal['summary', 'reply']
"""`summary`: what the ticket is about and where it stands; `reply`: a draft answer to the customer."""

ASSIST_TASKS: tuple[AssistTask, ...] = ('summary', 'reply')


@dataclass(frozen=True, kw_only=True)
class AssistLine:
    """One message of the ticket as the assistant reads it."""

    author: str
    from_customer: bool
    internal: bool
    body: str


@dataclass(frozen=True, kw_only=True)
class AssistInput:
    task: AssistTask
    subject: str
    customer: str | None
    lines: tuple[AssistLine, ...]
    agent: str
    """Who asks; a reply draft is signed with this name."""
