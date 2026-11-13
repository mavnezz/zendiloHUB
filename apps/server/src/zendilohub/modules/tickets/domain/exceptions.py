from zendilohub.core.domain.app_domain_error import ConflictError, ForbiddenError, NotFoundError, ValidationError
from zendilohub.core.domain.queue_rights import QueueRight


class InvalidTicketError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_ticket', f'Please check the ticket ({field})', {'field': field})


class InvalidMessageError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_message', f'Please check the message ({field})', {'field': field})


class TicketNotFoundError(NotFoundError):
    """Also for tickets in queues the caller may not see."""

    def __init__(self) -> None:
        super().__init__('ticket_not_found', 'The ticket does not exist')


class MessageNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('message_not_found', 'The message does not exist')


class QueueRightMissingError(ForbiddenError):
    def __init__(self, right: QueueRight) -> None:
        super().__init__('queue_right_missing', 'Your groups do not allow this in this queue', {'right': right})


class NotAssignableError(ValidationError):
    """Tickets go only to people who may reply in their queue."""

    def __init__(self) -> None:
        super().__init__('not_assignable', 'This person may not reply in the queue of the ticket')


class TicketMergedError(ConflictError):
    def __init__(self) -> None:
        super().__init__('ticket_merged', 'The ticket was merged into another one')


class MergeIntoItselfError(ValidationError):
    def __init__(self) -> None:
        super().__init__('merge_into_itself', 'A ticket cannot be merged into itself')


class LinkToItselfError(ValidationError):
    def __init__(self) -> None:
        super().__init__('link_to_itself', 'A ticket cannot be linked to itself')
