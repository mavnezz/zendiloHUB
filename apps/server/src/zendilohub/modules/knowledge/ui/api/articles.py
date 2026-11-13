from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.http.access import CurrentMember, Member, Public, member_with
from zendilohub.core.http.audit import Unaudited, audited, note_audit
from zendilohub.core.http.ids import Id

from ...application.commands.articles import DeleteArticle, GetArticle, Library, SaveArticle, SearchArticles
from ...domain.models.article import Article

Editor = Annotated[Member, member_with('knowledge.manage')]


class ArticleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str = Field(max_length=200)
    body: str = Field(max_length=100_000)
    """Plain text with Markdown (headings, lists, links)."""
    category: str = Field(default='', max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    visibility: Literal['internal', 'public'] = 'internal'
    """`public` articles show in the help center for customers."""


class ArticleResponse(BaseModel):
    id: str
    title: str
    body: str
    category: str
    tags: list[str]
    visibility: Literal['internal', 'public']
    author: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, article: Article) -> ArticleResponse:
        return cls(
            id=article.id,
            title=article.title,
            body=article.body,
            category=article.category,
            tags=list(article.tags),
            visibility=article.visibility,
            author=article.author,
            created_at=article.created_at,
            updated_at=article.updated_at,
        )


class LibraryResponse(BaseModel):
    articles: list[ArticleResponse]
    categories: list[str]

    @classmethod
    def of(cls, library: Library) -> LibraryResponse:
        return cls(
            articles=[ArticleResponse.of(each) for each in library.articles], categories=list(library.categories)
        )


def article_routes(bus: CommandBus) -> APIRouter:
    router = APIRouter(prefix='/tenants/{tenant_id}', tags=['knowledge'])

    @router.get('/articles')
    async def articles(
        member: CurrentMember,
        q: Annotated[str, Query(max_length=200)] = '',
        category: Annotated[str | None, Query(max_length=80)] = None,
    ) -> LibraryResponse:
        """The knowledge base (internal and public articles); `q` searches title, text and tags."""
        return LibraryResponse.of(
            await bus.query(SearchArticles(tenant_id=member.tenant_id, query=q, category=category))
        )

    @router.get('/articles/{article_id}')
    async def article(article_id: Id, member: CurrentMember) -> ArticleResponse:
        return ArticleResponse.of(await bus.query(GetArticle(tenant_id=member.tenant_id, article_id=article_id)))

    @router.post('/articles', status_code=201, dependencies=[audited('article.created')])
    async def create(body: ArticleRequest, request: Request, member: Editor) -> ArticleResponse:
        article = await bus.execute(
            SaveArticle(
                tenant_id=member.tenant_id,
                title=body.title,
                body=body.body,
                category=body.category,
                tags=tuple(body.tags),
                visibility=body.visibility,
                author=member.principal.email,
            )
        )
        note_audit(request, target=article.title)
        return ArticleResponse.of(article)

    @router.patch('/articles/{article_id}', dependencies=[audited('article.updated')])
    async def update(article_id: Id, body: ArticleRequest, request: Request, member: Editor) -> ArticleResponse:
        article = await bus.execute(
            SaveArticle(
                tenant_id=member.tenant_id,
                title=body.title,
                body=body.body,
                category=body.category,
                tags=tuple(body.tags),
                visibility=body.visibility,
                article_id=article_id,
            )
        )
        note_audit(request, target=article.title)
        return ArticleResponse.of(article)

    @router.delete(
        '/articles/{article_id}', status_code=204, response_class=Response, dependencies=[audited('article.deleted')]
    )
    async def delete(article_id: Id, request: Request, member: Editor) -> None:
        article = await bus.execute(DeleteArticle(tenant_id=member.tenant_id, article_id=article_id))
        note_audit(request, target=article.title)

    return router


def help_center_routes(bus: CommandBus) -> APIRouter:
    """The help center: an organization's public articles, readable by anyone (no login)."""
    router = APIRouter(prefix='/help/{tenant_id}', tags=['knowledge'])

    @router.get('', dependencies=[Public, Unaudited])
    async def library(
        tenant_id: Id,
        q: Annotated[str, Query(max_length=200)] = '',
        category: Annotated[str | None, Query(max_length=80)] = None,
    ) -> LibraryResponse:
        found = await bus.query(SearchArticles(tenant_id=tenant_id, query=q, category=category, public_only=True))
        return LibraryResponse.of(found)

    @router.get('/{article_id}', dependencies=[Public, Unaudited])
    async def public_article(tenant_id: Id, article_id: Id) -> ArticleResponse:
        return ArticleResponse.of(
            await bus.query(GetArticle(tenant_id=tenant_id, article_id=article_id, public_only=True))
        )

    return router
