from datetime import UTC, datetime

from zendilohub.modules.identity.domain.models import totp
from zendilohub.modules.identity.domain.models.login_challenge import LoginChallenge

# The secret of RFC 6238's SHA-1 test vectors ("12345678901234567890"), in base32.
RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def test_matches_the_rfc_6238_vectors() -> None:
    # The RFC lists 8 digits; authenticator apps show the last 6.
    for seconds, expected in (
        (59, '94287082'),
        (1111111109, '07081804'),
        (1111111111, '14050471'),
        (1234567890, '89005924'),
        (2000000000, '69279037'),
        (20000000000, '65353130'),
    ):
        assert totp.code_at(RFC_SECRET, totp.step_at(at(seconds))) == expected[-6:]


def test_accepts_the_neighboring_steps_and_no_used_ones() -> None:
    now = at(1111111111)
    step = totp.step_at(now)
    for offset in (-1, 0, 1):
        assert totp.matching_step(RFC_SECRET, totp.code_at(RFC_SECRET, step + offset), now, after=0) == step + offset
    assert totp.matching_step(RFC_SECRET, totp.code_at(RFC_SECRET, step + 2), now, after=0) is None
    assert totp.matching_step(RFC_SECRET, totp.code_at(RFC_SECRET, step), now, after=step) is None
    spaced = totp.code_at(RFC_SECRET, step)
    assert totp.matching_step(RFC_SECRET, f'{spaced[:3]} {spaced[3:]}', now, after=0) == step
    assert totp.matching_step(RFC_SECRET, 'abcdef', now, after=0) is None
    assert totp.matching_step(RFC_SECRET, '\uff11\uff12\uff13\uff14\uff15\uff16', now, after=0) is None


def test_makes_secrets_and_recovery_codes() -> None:
    secret = totp.new_secret()
    assert len(secret) == 32
    assert secret != totp.new_secret()
    assert totp.code_at(secret, 1).isdigit()
    codes = totp.new_recovery_codes()
    assert len(codes) == 10
    assert all(len(code) == 9 and code[4] == '-' for code in codes)
    assert totp.hash_recovery_code(codes[0]) == totp.hash_recovery_code(f' {codes[0].upper().replace("-", " ")} ')
    assert totp.provisioning_uri('ABC', 'a b@example.org').startswith('otpauth://totp/zendiloHUB:a%20b@example.org?')


def test_a_challenge_counts_attempts() -> None:
    challenge = LoginChallenge.start(id='x', user_id='u', now=at(0))
    assert not challenge.is_expired(at(299))
    assert challenge.is_expired(at(300))
    assert [challenge.fail() for _ in range(5)] == [True, True, True, True, False]
