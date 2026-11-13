from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from zendilohub.core.domain.app_domain_error import NotFoundError, ValidationError

type Visibility = Literal['internal', 'public']
ARTICLES_MAX = 2000


class InvalidArticleError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_article', f'Please check the article ({field})', {'field': field})


class ArticleNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('article_not_found', 'The article does not exist')


@dataclass(kw_only=True)
class Article:
    """
    An article of the knowledge base (like OTOBO's FAQ and Zammad's knowledge base): internal ones help the team,
    public ones show in the help center for customers.
    """

    id: str
    tenant_id: str
    title: str
    body: str
    category: str
    tags: tuple[str, ...]
    visibility: Visibility
    author: str
    created_at: datetime
    updated_at: datetime

    def check(self) -> None:
        self.title, self.category = ' '.join(self.title.split()), ' '.join(self.category.split())
        self.body = self.body.strip('\n').rstrip()
        self.tags = tuple(sorted({' '.join(tag.split()).lower() for tag in self.tags if tag.strip()}))
        if not 1 <= len(self.title) <= 200:
            raise InvalidArticleError('title')
        if not self.body.strip() or len(self.body) > 100_000:
            raise InvalidArticleError('body')
        if len(self.category) > 80:
            raise InvalidArticleError('category')
        if len(self.tags) > 20 or any(len(tag) > 50 for tag in self.tags):
            raise InvalidArticleError('tags')
        if self.visibility not in ('internal', 'public'):
            raise InvalidArticleError('visibility')
