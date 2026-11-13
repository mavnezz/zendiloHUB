from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...domain.models.user import User
from ...domain.ports.user_repository import UserPage

type LocaleValue = Literal['de', 'en']
type RoleValue = Literal['user', 'admin']


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RegisterRequest(Request):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)
    locale: LocaleValue = 'en'


class SetupRequest(Request):
    token: str = Field(max_length=100)
    """The setup code from the server's log."""
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)
    organization_name: str = Field(max_length=200)
    timezone: str = Field(max_length=64)
    locale: LocaleValue = 'en'


class SetupStatusResponse(BaseModel):
    open: bool
    """True while a self-hosted instance has no administrator: the web app shows the setup wizard."""
    self_hosted: bool
    """One organization, sign-up for invited people only; False: SaaS (everyone signs up, many organizations)."""


class CredentialsRequest(Request):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class TokenRequest(Request):
    token: str = Field(max_length=256)


class EmailRequest(Request):
    email: str = Field(max_length=254)


class ResetPasswordRequest(Request):
    token: str = Field(max_length=256)
    password: str = Field(max_length=1024)


class UpdateAccountRequest(Request):
    locale: LocaleValue


class ChangePasswordRequest(Request):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class PasswordRequest(Request):
    password: str = Field(max_length=1024)


class UpdateUserRequest(Request):
    role: RoleValue


class UserResponse(BaseModel):
    id: str
    email: str
    role: RoleValue
    locale: LocaleValue
    created_at: datetime

    @classmethod
    def of(cls, user: User) -> UserResponse:
        return cls(id=user.id, email=user.email, role=user.role, locale=user.locale, created_at=user.created_at)


class SessionResponse(BaseModel):
    user: UserResponse | None


class UserPageResponse(BaseModel):
    items: list[UserResponse]
    total: int

    @classmethod
    def of(cls, page: UserPage) -> UserPageResponse:
        return cls(items=[UserResponse.of(user) for user in page.items], total=page.total)
