from collections.abc import Sequence
from typing import Protocol

from ..models.text_module import TextModule


class TextModuleRepository(Protocol):
    async def of_tenant(self, tenant_id: str) -> Sequence[TextModule]:
        """By keyword."""
        ...

    async def find(self, tenant_id: str, module_id: str) -> TextModule | None: ...

    async def save(self, module: TextModule) -> None: ...

    async def delete(self, tenant_id: str, module_id: str) -> None: ...

    async def forget_queue(self, tenant_id: str, queue_id: str) -> None:
        """A queue is gone: modules limited to it lose it from their list."""
        ...

    async def forget_tenant(self, tenant_id: str) -> None: ...
