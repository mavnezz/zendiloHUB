from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.files import FileData
from zendilohub.core.domain.rate_limited import TooManyRequestsError
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

from ...domain.exceptions import AttachmentNotFoundError, QueueRightMissingError, TicketMergedError
from ...domain.models.actor import Actor
from ...domain.models.attachment import Attachment
from ..services.desk import Desk
from ..services.files import Files

UPLOADS_PER_PERSON = RateLimit('ticket-uploads', limit=200, window_seconds=60 * 60)


@dataclass(frozen=True, kw_only=True)
class UploadAttachment(Command[Attachment]):
    """A file for the reply or note being written (`note` or `reply`); it waits until the message takes it."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    file: FileData


class UploadAttachmentHandler:
    def __init__(self, desk: Desk, files: Files, limiter: RateLimiter) -> None:
        self._desk = desk
        self._files = files
        self._limiter = limiter

    async def handle(self, command: UploadAttachment) -> Attachment:
        ticket, rights = await self._desk.load(command.tenant_id, command.actor, command.ticket_id)
        if ticket.is_merged:
            raise TicketMergedError()
        if not rights & {'note', 'reply'}:
            raise QueueRightMissingError('reply')
        self._files.check_size(len(command.file.content))
        status = await self._limiter.hit(UPLOADS_PER_PERSON, f'{command.tenant_id}:{command.actor.user_id}')
        if not status.allowed:
            raise TooManyRequestsError(status.retry_after)
        return await self._files.add(
            ticket.tenant_id, ticket.id, command.file, message_id=None, created_by=command.actor.user_id
        )


async def _visible(desk: Desk, files: Files, tenant_id: str, actor: Actor, ticket_id: str, file_id: str) -> Attachment:
    ticket, _rights = await desk.load(tenant_id, actor, ticket_id)
    attachment = await files.attachments.find(ticket.tenant_id, file_id)
    if (
        attachment is None
        or attachment.ticket_id != ticket.id
        # Pending uploads are their uploader's alone.
        or (attachment.message_id is None and attachment.created_by != actor.user_id)
    ):
        raise AttachmentNotFoundError()
    return attachment


@dataclass(frozen=True, kw_only=True)
class DeleteAttachment(Command[None]):
    """Takes back an upload that no message took yet."""

    tenant_id: str
    actor: Actor
    ticket_id: str
    attachment_id: str


class DeleteAttachmentHandler:
    def __init__(self, desk: Desk, files: Files) -> None:
        self._desk = desk
        self._files = files

    async def handle(self, command: DeleteAttachment) -> None:
        attachment = await _visible(
            self._desk, self._files, command.tenant_id, command.actor, command.ticket_id, command.attachment_id
        )
        if attachment.message_id is not None:
            raise AttachmentNotFoundError()
        await self._files.remove(attachment)


@dataclass(frozen=True)
class AttachmentFile:
    attachment: Attachment
    content: bytes


@dataclass(frozen=True, kw_only=True)
class GetAttachment(Query[AttachmentFile]):
    tenant_id: str
    actor: Actor
    ticket_id: str
    attachment_id: str


class GetAttachmentHandler:
    def __init__(self, desk: Desk, files: Files) -> None:
        self._desk = desk
        self._files = files

    async def handle(self, query: GetAttachment) -> AttachmentFile:
        attachment = await _visible(
            self._desk, self._files, query.tenant_id, query.actor, query.ticket_id, query.attachment_id
        )
        data = await self._files.content(attachment)
        if data is None:
            raise AttachmentNotFoundError()
        return AttachmentFile(attachment, data.content)


@dataclass(frozen=True)
class CleanAttachments(Command[int]):
    """A scheduled job: old pending uploads and files of deleted tickets go."""


class CleanAttachmentsHandler:
    def __init__(self, files: Files) -> None:
        self._files = files

    async def handle(self, command: CleanAttachments) -> int:
        return await self._files.clean()
