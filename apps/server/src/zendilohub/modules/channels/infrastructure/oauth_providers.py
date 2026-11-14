"""OAuth 2 at Google and Microsoft (Entra ID): authorization code with PKCE, refresh tokens, the address from the ID token."""

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from zendilohub.core.config import AppConfig, OAuthApp
from zendilohub.core.domain.http_fetch import FetchBlockedError, FetchFailedError, PublicFetcher

from ..domain.models.account import Provider
from ..domain.ports.services import OAuthError, TokenGrant

TIME_LIMIT = 20.0


@dataclass(frozen=True)
class _Endpoints:
    authorize: str
    token: str
    scope: str
    extra: dict[str, str]
    """More parameters of the sign-in page."""


def _endpoints(provider: Provider, microsoft_tenant: str) -> _Endpoints:
    if provider == 'google':
        return _Endpoints(
            authorize='https://accounts.google.com/o/oauth2/v2/auth',
            token='https://oauth2.googleapis.com/token',
            scope='openid email https://mail.google.com/',
            # A refresh token every time, also when the mailbox was connected before.
            extra={'access_type': 'offline', 'prompt': 'consent'},
        )
    base = f'https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0'
    return _Endpoints(
        authorize=f'{base}/authorize',
        token=f'{base}/token',
        scope=(
            'openid email offline_access https://outlook.office.com/IMAP.AccessAsUser.All '
            'https://outlook.office.com/SMTP.Send'
        ),
        extra={'prompt': 'select_account'},
    )


def address_from_id_token(id_token: str | None) -> str | None:
    """
    The mailbox's address. The token comes straight from the provider's token endpoint over TLS, so its signature
    need not be checked (OpenID Connect Core 3.1.3.7).
    """
    if not id_token or id_token.count('.') != 2:
        return None
    payload = id_token.split('.')[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except ValueError:
        return None
    if not isinstance(claims, dict) or claims.get('email_verified') is False:
        return None
    for claim in ('email', 'preferred_username', 'upn'):
        value = claims.get(claim)
        if isinstance(value, str) and '@' in value:
            return value
    return None


class HttpOAuthProviders:
    def __init__(self, config: AppConfig, fetcher: PublicFetcher) -> None:
        self._apps: dict[Provider, OAuthApp] = {}
        if config.google_oauth:
            self._apps['google'] = config.google_oauth
        if config.microsoft_oauth:
            self._apps['microsoft'] = config.microsoft_oauth
        self._tenant = config.microsoft_tenant
        self._fetcher = fetcher

    def configured(self) -> tuple[Provider, ...]:
        return tuple(self._apps)

    def authorize_url(self, provider: Provider, *, state: str, challenge: str, redirect_uri: str) -> str:
        endpoints = _endpoints(provider, self._tenant)
        query = {
            'client_id': self._app(provider).client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': endpoints.scope,
            'state': state,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            **endpoints.extra,
        }
        return f'{endpoints.authorize}?{urlencode(query)}'

    async def exchange(self, provider: Provider, *, code: str, verifier: str, redirect_uri: str) -> TokenGrant:
        body = await self._token(
            provider,
            {'grant_type': 'authorization_code', 'code': code, 'code_verifier': verifier, 'redirect_uri': redirect_uri},
        )
        grant = self._grant(body)
        return TokenGrant(
            access_token=grant.access_token,
            expires_in=grant.expires_in,
            refresh_token=grant.refresh_token,
            address=address_from_id_token(body.get('id_token')),
        )

    async def refresh(self, provider: Provider, refresh_token: str) -> TokenGrant:
        return self._grant(await self._token(provider, {'grant_type': 'refresh_token', 'refresh_token': refresh_token}))

    def _app(self, provider: Provider) -> OAuthApp:
        app = self._apps.get(provider)
        if app is None:
            raise OAuthError('not_configured')
        return app

    async def _token(self, provider: Provider, fields: dict[str, str]) -> dict[str, Any]:
        app = self._app(provider)
        endpoints = _endpoints(provider, self._tenant)
        form = {**fields, 'client_id': app.client_id, 'client_secret': app.client_secret}
        if provider == 'microsoft':
            form['scope'] = endpoints.scope
        try:
            result = await self._fetcher.fetch(
                'POST',
                endpoints.token,
                content=urlencode(form).encode(),
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
                time_limit=TIME_LIMIT,
            )
        except FetchBlockedError, FetchFailedError:
            raise OAuthError('unreachable') from None
        try:
            body = json.loads(result.body)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise OAuthError(f'http_{result.status}')
        if result.status >= 400 or 'error' in body:
            error = body.get('error')
            raise OAuthError(error if isinstance(error, str) and error.isascii() else f'http_{result.status}')
        return body

    @staticmethod
    def _grant(body: dict[str, Any]) -> TokenGrant:
        access, refresh, expires_in = body.get('access_token'), body.get('refresh_token'), body.get('expires_in', 3600)
        if not isinstance(access, str) or not access:
            raise OAuthError('no_access_token')
        return TokenGrant(
            access_token=access,
            expires_in=int(expires_in) if isinstance(expires_in, (int, str)) and str(expires_in).isdigit() else 3600,
            refresh_token=refresh if isinstance(refresh, str) and refresh else None,
        )
