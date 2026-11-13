from collections.abc import Sequence
from typing import Protocol

from ..models.article import Article
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


class ArticleRepository(Protocol):
    async def search(
        self, tenant_id: str, query: str, *, category: str | None, public_only: bool, limit: int
    ) -> Sequence[Article]:
        """Title, text and tags containing `query`, most recently changed first."""
        ...

    async def categories(self, tenant_id: str, *, public_only: bool) -> Sequence[str]: ...

    async def find(self, tenant_id: str, article_id: str) -> Article | None: ...

    async def count(self, tenant_id: str) -> int: ...

    async def save(self, article: Article) -> None: ...

    async def delete(self, tenant_id: str, article_id: str) -> None: ...
