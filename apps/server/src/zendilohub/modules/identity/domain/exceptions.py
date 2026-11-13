from zendilohub.core.domain.app_domain_error import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthenticatedError,
    ValidationError,
)


class InvalidEmailError(ValidationError):
    def __init__(self) -> None:
        super().__init__('invalid_email', 'This is not a valid e-mail address')


class WeakPasswordError(ValidationError):
    def __init__(self, min_length: int, max_length: int) -> None:
        super().__init__(
            'weak_password',
            f'The password must have between {min_length} and {max_length} characters',
            {'min_length': min_length, 'max_length': max_length},
        )


class EmailTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('email_taken', 'An account with this e-mail address already exists')


class InvalidCredentialsError(UnauthenticatedError):
    def __init__(self) -> None:
        super().__init__('invalid_credentials', 'E-mail address or password is wrong')


class EmailNotVerifiedError(ForbiddenError):
    """The password matches a sign-up whose e-mail address is not confirmed yet."""

    def __init__(self) -> None:
        super().__init__('email_not_verified', 'Please confirm your e-mail address first')


class InvalidTokenError(ValidationError):
    """A confirmation or reset link is unknown, used or expired."""

    def __init__(self) -> None:
        super().__init__('invalid_token', 'This link is invalid or has expired')


class InvalidCurrentPasswordError(ValidationError):
    def __init__(self) -> None:
        super().__init__('invalid_current_password', 'The current password is wrong')


class UserNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('user_not_found', 'The user does not exist')


class LastAdminError(ConflictError):
    def __init__(self) -> None:
        super().__init__('last_admin', 'The last administrator cannot be removed or demoted')


class OwnAccountError(ConflictError):
    def __init__(self) -> None:
        super().__init__('own_account', 'Use the account page to change or delete your own account')


class SetupDoneError(ConflictError):
    """The instance has its administrator already; the setup wizard is closed for good."""

    def __init__(self) -> None:
        super().__init__('setup_done', 'This instance is set up already')


class InvalidSetupTokenError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__('invalid_setup_token', 'The setup code is wrong; it is in the log of the server')


class SignUpClosedError(ForbiddenError):
    """A self-hosted instance: only people an organization invited may create an account."""

    def __init__(self) -> None:
        super().__init__('sign_up_closed', 'Only invited people can create an account here')
