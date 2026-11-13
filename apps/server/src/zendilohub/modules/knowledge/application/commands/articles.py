from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.models.article import ARTICLES_MAX, Article, ArticleNotFoundError, InvalidArticleError, Visibility
from ...domain.ports.repositories import ArticleRepository


@dataclass(frozen=True, kw_only=True)
class SaveArticle(Command[Article]):
    tenant_id: str
    title: str
    body: str
    category: str = ''
    tags: tuple[str, ...] = ()
    visibility: Visibility = 'internal'
    author: str = ''
    article_id: str | None = None


class SaveArticleHandler:
    def __init__(self, articles: ArticleRepository, ids: IdGenerator, clock: Clock) -> None:
        self._articles = articles
        self._ids = ids
        self._clock = clock

    async def handle(self, command: SaveArticle) -> Article:
        now = self._clock.now()
        if command.article_id is None:
            if await self._articles.count(command.tenant_id) >= ARTICLES_MAX:
                raise InvalidArticleError('limit')
            article = Article(
                id=self._ids.new_id(),
                tenant_id=command.tenant_id,
                title=command.title,
                body=command.body,
                category=command.category,
                tags=command.tags,
                visibility=command.visibility,
                author=command.author,
                created_at=now,
                updated_at=now,
            )
        else:
            found = await self._articles.find(command.tenant_id, command.article_id)
            if found is None:
                raise ArticleNotFoundError()
            article = found
            article.title, article.body, article.category = command.title, command.body, command.category
            article.tags, article.visibility, article.updated_at = command.tags, command.visibility, now
        article.check()
        await self._articles.save(article)
        return article


@dataclass(frozen=True, kw_only=True)
class DeleteArticle(Command[Article]):
    tenant_id: str
    article_id: str


class DeleteArticleHandler:
    def __init__(self, articles: ArticleRepository) -> None:
        self._articles = articles

    async def handle(self, command: DeleteArticle) -> Article:
        found = await self._articles.find(command.tenant_id, command.article_id)
        if found is None:
            raise ArticleNotFoundError()
        await self._articles.delete(command.tenant_id, found.id)
        return found


@dataclass(frozen=True)
class Library:
    articles: Sequence[Article]
    categories: Sequence[str]


@dataclass(frozen=True, kw_only=True)
class SearchArticles(Query[Library]):
    tenant_id: str
    query: str = ''
    category: str | None = None
    public_only: bool = False
    limit: int = 100


class SearchArticlesHandler:
    def __init__(self, articles: ArticleRepository) -> None:
        self._articles = articles

    async def handle(self, query: SearchArticles) -> Library:
        found = await self._articles.search(
            query.tenant_id,
            query.query.strip(),
            category=query.category,
            public_only=query.public_only,
            limit=query.limit,
        )
        return Library(found, await self._articles.categories(query.tenant_id, public_only=query.public_only))


@dataclass(frozen=True, kw_only=True)
class GetArticle(Query[Article]):
    tenant_id: str
    article_id: str
    public_only: bool = False


class GetArticleHandler:
    def __init__(self, articles: ArticleRepository) -> None:
        self._articles = articles

    async def handle(self, query: GetArticle) -> Article:
        found = await self._articles.find(query.tenant_id, query.article_id)
        if found is None or (query.public_only and found.visibility != 'public'):
            raise ArticleNotFoundError()
        return found
