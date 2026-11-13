from ..exceptions import WeakPasswordError

MIN_LENGTH = 10
# Long enough for passphrases and password managers, short enough to keep hashing cheap.
MAX_LENGTH = 128


def check_password(password: str) -> None:
    if not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        raise WeakPasswordError(MIN_LENGTH, MAX_LENGTH)
