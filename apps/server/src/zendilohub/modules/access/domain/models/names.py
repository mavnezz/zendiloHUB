from ..exceptions import InvalidGroupError, InvalidQueueError

NAME_MAX = 80
DESCRIPTION_MAX = 500


def queue_text(name: str, description: str) -> tuple[str, str]:
    """A queue's name and description, trimmed; raises `InvalidQueueError` for an empty or too long one."""
    return _checked(name, description, InvalidQueueError)


def group_text(name: str, description: str) -> tuple[str, str]:
    return _checked(name, description, InvalidGroupError)


def _checked(name: str, description: str, error: type[InvalidQueueError] | type[InvalidGroupError]) -> tuple[str, str]:
    name, description = ' '.join(name.split()), description.strip()
    if not 1 <= len(name) <= NAME_MAX:
        raise error('name')
    if len(description) > DESCRIPTION_MAX:
        raise error('description')
    return name, description
