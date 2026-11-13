from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise ValueError('must be a UUID') from None


Id = Annotated[str, AfterValidator(_uuid)]
"""An id in a path, query or body: anything but a UUID is rejected with 422 before it reaches the database."""
