from zendilohub.core.domain.app_domain_error import ConflictError, NotFoundError, ValidationError


class InvalidQueueError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_queue', f'Please check the queue ({field})', {'field': field})


class InvalidGroupError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_group', f'Please check the group ({field})', {'field': field})


class QueueNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('queue_not_found', 'The queue does not exist')


class GroupNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('group_not_found', 'The group does not exist')


class QueueNameTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('queue_name_taken', 'There is already a queue of this name')


class GroupNameTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('group_name_taken', 'There is already a group of this name')


class QueueLimitError(ConflictError):
    def __init__(self, limit: int) -> None:
        super().__init__('queue_limit', f'An organization has at most {limit} queues', {'limit': limit})


class GroupLimitError(ConflictError):
    def __init__(self, limit: int) -> None:
        super().__init__('group_limit', f'An organization has at most {limit} groups', {'limit': limit})


class NotAMemberError(ValidationError):
    """Only members of the organization can be in its groups."""

    def __init__(self, user_id: str) -> None:
        super().__init__('not_a_member', 'This person is no member of the organization', {'user_id': user_id})


class InvalidRightsError(ValidationError):
    def __init__(self, right: str) -> None:
        super().__init__('invalid_rights', f'"{right}" is no right in a queue', {'right': right})
