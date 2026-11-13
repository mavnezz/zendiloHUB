import hmac
import secrets
from pathlib import Path

FILE_NAME = 'setup-token'


class FileSetupTokens:
    """Keeps the setup code in the data directory, so it survives restarts and every process sees the same one."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / FILE_NAME

    def issue(self) -> str:
        if self._path.exists():
            return self._path.read_text('utf-8').strip()
        token = '-'.join(secrets.token_hex(3) for _ in range(3))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(f'{token}\n', 'utf-8')
        self._path.chmod(0o600)
        return token

    def matches(self, token: str) -> bool:
        if not self._path.exists():
            return False
        return hmac.compare_digest(self._path.read_text('utf-8').strip(), token.strip().lower())

    def discard(self) -> None:
        self._path.unlink(missing_ok=True)
