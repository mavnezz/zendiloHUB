from typing import Final


class Unset:
    """A field the caller did not send (unlike None, which clears it)."""

    _instance: Unset | None = None

    def __new__(cls) -> Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return 'UNSET'

    def __bool__(self) -> bool:
        return False


UNSET: Final = Unset()
