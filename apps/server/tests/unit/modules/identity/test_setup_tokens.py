from pathlib import Path

from zendilohub.modules.identity.infrastructure.setup_token import FileSetupTokens


def test_keeps_one_code_until_the_setup_is_done(tmp_path: Path) -> None:
    tokens = FileSetupTokens(tmp_path / 'data')
    assert not tokens.matches('anything')

    code = tokens.issue()
    assert tokens.issue() == code
    assert FileSetupTokens(tmp_path / 'data').matches(f' {code.upper()} ')
    assert not tokens.matches('000000-000000-000000')

    tokens.discard()
    assert not tokens.matches(code)
    assert tokens.issue() != code
