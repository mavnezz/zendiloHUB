from zendilohub.modules.channels.domain.models.account import Provider
from zendilohub.modules.channels.domain.ports.services import OAuthError, TokenGrant


class FakeOAuth:
    """Stands in for Google and Microsoft: hands out numbered tokens and remembers what it was asked."""

    def __init__(self) -> None:
        self.providers: tuple[Provider, ...] = ('google', 'microsoft')
        self.address = 'support@acme.example'
        self.exchanged: list[tuple[Provider, str, str, str]] = []
        """(provider, code, verifier, redirect URI)."""
        self.refreshed: list[tuple[Provider, str]] = []
        self.exchange_error: str | None = None
        self.refresh_error: str | None = None
        self.rotate = True
        self.expires_in = 3600
        self._count = 0

    def configured(self) -> tuple[Provider, ...]:
        return self.providers

    def authorize_url(self, provider: Provider, *, state: str, challenge: str, redirect_uri: str) -> str:
        return f'https://{provider}.test/authorize?state={state}&challenge={challenge}&redirect_uri={redirect_uri}'

    async def exchange(self, provider: Provider, *, code: str, verifier: str, redirect_uri: str) -> TokenGrant:
        self.exchanged.append((provider, code, verifier, redirect_uri))
        if self.exchange_error:
            raise OAuthError(self.exchange_error)
        self._count += 1
        return TokenGrant(
            access_token=f'access-{self._count}',
            expires_in=self.expires_in,
            refresh_token=f'refresh-{self._count}',
            address=self.address,
        )

    async def refresh(self, provider: Provider, refresh_token: str) -> TokenGrant:
        self.refreshed.append((provider, refresh_token))
        if self.refresh_error:
            raise OAuthError(self.refresh_error)
        self._count += 1
        return TokenGrant(
            access_token=f'access-{self._count}',
            expires_in=self.expires_in,
            refresh_token=f'refresh-{self._count}' if self.rotate else None,
        )
