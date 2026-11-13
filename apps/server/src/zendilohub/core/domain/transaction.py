from contextlib import AbstractAsyncContextManager
from typing import Protocol


class TransactionManager(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[None]:
        """Everything the repositories do inside the block commits or rolls back together."""
        ...
