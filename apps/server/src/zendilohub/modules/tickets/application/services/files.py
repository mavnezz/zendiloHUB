import hashlib
from collections.abc import Sequence
from datetime import timedelta

from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.files import FileData, FileInfo
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.exceptions import AttachmentTooLargeError, InvalidMessageError
from ...domain.models.attachment import PER_MESSAGE, Attachment, clean_content_type, clean_filename
from ...domain.models.message import Message
from ...domain.ports.repositories import AttachmentRepository
from ...domain.ports.services import FileStore

PENDING_HOURS = 24
"""Uploads no message took are deleted after this long."""
CLEANUP_BATCH = 500


def info(attachment: Attachment) -> FileInfo:
    return FileInfo(
        id=attachment.id, filename=attachment.filename, content_type=attachment.content_type, size=attachment.size
    )


class Files:
    """Attachments: their rows and their content, which lives in the file store."""

    def __init__(
        self, attachments: AttachmentRepository, store: FileStore, ids: IdGenerator, clock: Clock, max_bytes: int
    ) -> None:
        self.attachments = attachments
        self._store = store
        self._ids = ids
        self._clock = clock
        self.max_bytes = max_bytes

    def check_size(self, size: int) -> None:
        if size > self.max_bytes:
            raise AttachmentTooLargeError(self.max_bytes // (1024 * 1024))

    async def add(
        self, tenant_id: str, ticket_id: str, file: FileData, *, message_id: str | None, created_by: str | None
    ) -> Attachment:
        self.check_size(len(file.content))
        attachment = Attachment(
            id=self._ids.new_id(),
            tenant_id=tenant_id,
            ticket_id=ticket_id,
            message_id=message_id,
            filename=clean_filename(file.filename),
            content_type=clean_content_type(file.content_type),
            size=len(file.content),
            sha256=hashlib.sha256(file.content).hexdigest(),
            content_id=(file.content_id or '').strip('<> ')[:250] or None,
            created_by=created_by,
            created_at=self._clock.now(),
        )
        # The content first: a row never points at nothing; content without a row is cleaned up.
        await self._store.put(tenant_id, attachment.id, file.content)
        await self.attachments.save(attachment)
        return attachment

    async def add_all(self, message: Message, files: Sequence[FileData], *, created_by: str | None = None) -> None:
        """Files that came with a message (e-mail, portal)."""
        if len(files) > PER_MESSAGE:
            raise InvalidMessageError('attachments')
        added = [
            await self.add(message.tenant_id, message.ticket_id, file, message_id=message.id, created_by=created_by)
            for file in files
        ]
        message.attachments = tuple(added)

    async def take(self, message: Message, attachment_ids: Sequence[str], user_id: str) -> None:
        """Pending uploads of the member go to their new message."""
        wanted = list(dict.fromkeys(attachment_ids))
        if not wanted:
            return
        if len(wanted) > PER_MESSAGE:
            raise InvalidMessageError('attachments')
        found = [await self.attachments.find(message.tenant_id, each) for each in wanted]
        taken = [
            each
            for each in found
            if each is not None
            and each.ticket_id == message.ticket_id
            and each.message_id is None
            and each.created_by == user_id
        ]
        if len(taken) != len(wanted):
            raise InvalidMessageError('attachments')
        await self.attachments.link(message.tenant_id, wanted, message.id)
        for each in taken:
            each.message_id = message.id
        message.attachments = tuple(taken)

    async def content(self, attachment: Attachment) -> FileData | None:
        content = await self._store.get(attachment.tenant_id, attachment.id)
        if content is None:
            return None
        return FileData(
            filename=attachment.filename,
            content_type=attachment.content_type,
            content=content,
            content_id=attachment.content_id,
        )

    async def remove(self, attachment: Attachment) -> None:
        await self.attachments.delete(attachment.tenant_id, attachment.id)
        await self._store.delete(attachment.tenant_id, attachment.id)

    async def clean(self) -> int:
        """Deletes old pending uploads and content whose row is gone (deleted tickets and organizations)."""
        before = self._clock.now() - timedelta(hours=PENDING_HOURS)
        removed = 0
        for attachment in await self.attachments.pending_before(before, CLEANUP_BATCH):
            await self.remove(attachment)
            removed += 1
        stored = list(self._store.stored(before))
        for start in range(0, len(stored), CLEANUP_BATCH):
            batch = stored[start : start + CLEANUP_BATCH]
            known = await self.attachments.known(batch)
            for tenant_id, file_id in batch:
                if (tenant_id, file_id) not in known:
                    await self._store.delete(tenant_id, file_id)
                    removed += 1
        return removed
