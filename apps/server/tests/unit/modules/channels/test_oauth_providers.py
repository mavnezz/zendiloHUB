"""The Google and Microsoft OAuth adapter against recorded answers of their token endpoints."""

import base64
import json
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from support.fakes import FakeWebsites
from zendilohub.core.config import OAuthApp, load_config
from zendilohub.core.domain.http_fetch import FetchFailedError
from zendilohub.modules.channels.domain.ports.services import OAuthError
from zendilohub.modules.channels.infrastructure.oauth_providers import HttpOAuthProviders, address_from_id_token

GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
MICROSOFT_TOKEN = 'https://login.microsoftonline.com/contoso/oauth2/v2.0/token'
REDIRECT = 'https://help.example.org/api/v1/email-oauth/callback'


def id_token(**claims: Any) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
    return f'eyJhbGciOiJSUzI1NiJ9.{payload}.signature'


def providers(websites: FakeWebsites) -> HttpOAuthProviders:
    config = replace(
        load_config({}),
        google_oauth=OAuthApp(client_id='g-id', client_secret='g-secret'),
        microsoft_oauth=OAuthApp(client_id='m-id', client_secret='m-secret'),
        microsoft_tenant='contoso',
    )
    return HttpOAuthProviders(config, websites)


def form(websites: FakeWebsites, url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(websites.to(url)[-1].body.decode()).items()}


def test_offers_only_configured_providers() -> None:
    assert HttpOAuthProviders(load_config({}), FakeWebsites()).configured() == ()
    assert providers(FakeWebsites()).configured() == ('google', 'microsoft')


def test_builds_the_sign_in_pages() -> None:
    oauth = providers(FakeWebsites())
    google = urlsplit(oauth.authorize_url('google', state='s1', challenge='c1', redirect_uri=REDIRECT))
    query = {key: values[0] for key, values in parse_qs(google.query).items()}
    assert google.netloc == 'accounts.google.com'
    assert query == {
        'client_id': 'g-id',
        'response_type': 'code',
        'redirect_uri': REDIRECT,
        'scope': 'openid email https://mail.google.com/',
        'state': 's1',
        'code_challenge': 'c1',
        'code_challenge_method': 'S256',
        'access_type': 'offline',
        'prompt': 'consent',
    }
    microsoft = urlsplit(oauth.authorize_url('microsoft', state='s2', challenge='c2', redirect_uri=REDIRECT))
    assert microsoft.path == '/contoso/oauth2/v2.0/authorize'
    assert 'https://outlook.office.com/SMTP.Send' in parse_qs(microsoft.query)['scope'][0]
    assert 'offline_access' in parse_qs(microsoft.query)['scope'][0]


async def test_exchanges_the_code() -> None:
    websites = FakeWebsites()
    body = {
        'access_token': 'a1',
        'expires_in': 3599,
        'refresh_token': 'r1',
        'id_token': id_token(email='me@acme.example'),
    }
    websites.answer(GOOGLE_TOKEN, body=json.dumps(body).encode(), content_type='application/json')
    grant = await providers(websites).exchange('google', code='c', verifier='v', redirect_uri=REDIRECT)
    assert (grant.access_token, grant.expires_in, grant.refresh_token, grant.address) == (
        'a1',
        3599,
        'r1',
        'me@acme.example',
    )
    assert form(websites, GOOGLE_TOKEN) == {
        'grant_type': 'authorization_code',
        'code': 'c',
        'code_verifier': 'v',
        'redirect_uri': REDIRECT,
        'client_id': 'g-id',
        'client_secret': 'g-secret',
    }


async def test_refreshes_at_microsoft() -> None:
    websites = FakeWebsites()
    websites.answer(MICROSOFT_TOKEN, body=json.dumps({'access_token': 'a2', 'expires_in': '3600'}).encode())
    grant = await providers(websites).refresh('microsoft', 'r1')
    assert (grant.access_token, grant.expires_in, grant.refresh_token, grant.address) == ('a2', 3600, None, None)
    sent = form(websites, MICROSOFT_TOKEN)
    assert (sent['grant_type'], sent['refresh_token'], sent['client_id']) == ('refresh_token', 'r1', 'm-id')
    assert 'IMAP.AccessAsUser.All' in sent['scope']


@pytest.mark.parametrize(
    ('status', 'body', 'code'),
    [
        (
            400,
            b'{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}',
            'invalid_grant',
        ),
        (502, b'<html>Bad gateway</html>', 'http_502'),
        (500, b'{"error": 7}', 'http_500'),
        (200, b'{"token_type": "Bearer"}', 'no_access_token'),
    ],
)
async def test_explains_refusals(status: int, body: bytes, code: str) -> None:
    websites = FakeWebsites()
    websites.answer(GOOGLE_TOKEN, status=status, body=body)
    with pytest.raises(OAuthError) as raised:
        await providers(websites).refresh('google', 'r1')
    assert raised.value.code == code


async def test_reports_unreachable_and_unknown_providers() -> None:
    websites = FakeWebsites()
    websites.fail(GOOGLE_TOKEN, FetchFailedError('timeout'))
    with pytest.raises(OAuthError, match='unreachable'):
        await providers(websites).refresh('google', 'r1')
    with pytest.raises(OAuthError, match='not_configured'):
        await HttpOAuthProviders(load_config({}), websites).refresh('google', 'r1')


def test_reads_the_address_from_the_id_token() -> None:
    assert address_from_id_token(id_token(email='a@acme.example')) == 'a@acme.example'
    assert address_from_id_token(id_token(preferred_username='b@acme.example', email=None)) == 'b@acme.example'
    assert address_from_id_token(id_token(email='a@acme.example', email_verified=False)) is None
    assert address_from_id_token(id_token(sub='123')) is None
    assert address_from_id_token(None) is None
    assert address_from_id_token('not-a-token') is None
    assert address_from_id_token('a.!!!.c') is None
    assert address_from_id_token(f'a.{base64.urlsafe_b64encode(b"[1]").decode()}.c') is None
