import httpx

from .app import AppUnderTest
from .fakes import MemoryOutput

PASSWORD = 'correct horse battery'


async def sign_up(app: AppUnderTest, email: str, password: str = PASSWORD, *, locale: str = 'en') -> str:
    """Signs up and returns the token of the confirmation link."""
    response = await app.client.post(
        '/api/v1/auth/register', json={'email': email, 'password': password, 'locale': locale}
    )
    assert response.status_code == 204, response.text
    return app.mailer.last_token(email)


async def logged_in(
    app: AppUnderTest, email: str, password: str = PASSWORD, *, client: httpx.AsyncClient | None = None
) -> httpx.AsyncClient:
    """A client with a session of a new, confirmed account."""
    token = await sign_up(app, email, password)
    client = client or app.new_client()
    response = await client.post('/api/v1/auth/confirm', json={'token': token})
    assert response.status_code == 200, response.text
    return client


async def make_admin(app: AppUnderTest, email: str) -> None:
    assert await app.app.run_command(['make-admin', email], MemoryOutput()) == 0
