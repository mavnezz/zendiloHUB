from collections.abc import Sequence
from typing import Any, cast

from zendilohub.core.database.database import Database

from ..domain.models.article import Article, Visibility


def _article(row: dict[str, Any]) -> Article:
    return Article(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        title=row['title'],
        body=row['body'],
        category=row['category'],
        tags=tuple(row['tags']),
        visibility=cast(Visibility, row['visibility']),
        author=row['author'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


class PostgresArticleRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def search(
        self, tenant_id: str, query: str, *, category: str | None, public_only: bool, limit: int
    ) -> Sequence[Article]:
        like = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        rows = await self._run(
            """
            SELECT * FROM knowledge_articles
            WHERE tenant_id = %(tenant)s
              AND (NOT %(public)s OR visibility = 'public')
              AND (%(category)s::text IS NULL OR category = %(category)s)
              AND (%(query)s = '' OR title ILIKE %(like)s OR search @@ plainto_tsquery('simple', %(query)s)
                   OR lower(%(query)s) = ANY(tags))
            ORDER BY updated_at DESC, id DESC LIMIT %(limit)s
            """,
            {
                'tenant': tenant_id,
                'public': public_only,
                'category': category,
                'query': query,
                'like': like,
                'limit': limit,
            },
        )
        return [_article(row) for row in rows]

    async def categories(self, tenant_id: str, *, public_only: bool) -> Sequence[str]:
        rows = await self._run(
            """
            SELECT DISTINCT category FROM knowledge_articles
            WHERE tenant_id = %s AND category <> '' AND (NOT %s OR visibility = 'public') ORDER BY category
            """,
            (tenant_id, public_only),
        )
        return [row['category'] for row in rows]

    async def find(self, tenant_id: str, article_id: str) -> Article | None:
        rows = await self._run(
            'SELECT * FROM knowledge_articles WHERE tenant_id = %s AND id = %s', (tenant_id, article_id)
        )
        return _article(rows[0]) if rows else None

    async def count(self, tenant_id: str) -> int:
        rows = await self._run('SELECT count(*) AS n FROM knowledge_articles WHERE tenant_id = %s', (tenant_id,))
        return int(rows[0]['n'])

    async def save(self, article: Article) -> None:
        await self._run(
            """
            INSERT INTO knowledge_articles (id, tenant_id, title, body, category, tags, visibility, author, created_at,
                                            updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(title)s, %(body)s, %(category)s, %(tags)s, %(visibility)s, %(author)s,
                    %(created_at)s, %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title, body = EXCLUDED.body, category = EXCLUDED.category, tags = EXCLUDED.tags,
                visibility = EXCLUDED.visibility, updated_at = EXCLUDED.updated_at
            """,
            vars(article) | {'tags': list(article.tags)},
        )

    async def delete(self, tenant_id: str, article_id: str) -> None:
        await self._run('DELETE FROM knowledge_articles WHERE tenant_id = %s AND id = %s', (tenant_id, article_id))
