from zendilohub.core.domain.app_domain_error import ConflictError, NotFoundError, ValidationError


class InvalidAccountError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_account', f'Please check the e-mail account ({field})', {'field': field})


class AccountNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('account_not_found', 'The e-mail account does not exist')


class AccountAddressTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('account_address_taken', 'Another e-mail account has this address already')


class InvalidTemplateError(ValidationError):
    def __init__(self, field: str, placeholder: str | None = None) -> None:
        params = {'field': field, **({'placeholder': placeholder} if placeholder else {})}
        super().__init__('invalid_template', f'Please check the text ({field})', params)


class TemplateNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('template_not_found', 'The signature or salutation does not exist')


class TemplateInUseError(ConflictError):
    def __init__(self) -> None:
        super().__init__('template_in_use', 'Queues still use this text; choose another one there first')


class InvalidFilterError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_filter', f'Please check the filter ({field})', {'field': field})


class FilterNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('filter_not_found', 'The filter does not exist')


class FailedEmailNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('failed_email_not_found', 'The e-mail does not exist')


class InvalidQueueSettingsError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_queue_settings', f'Please check the queue settings ({field})', {'field': field})


class OAuthUnavailableError(ValidationError):
    """The instance has no app credentials for this provider (ZENDILOHUB_<PROVIDER>_CLIENT_ID/_SECRET)."""

    def __init__(self, provider: str) -> None:
        super().__init__('oauth_unavailable', f'Connecting with {provider} is not set up here', {'provider': provider})


class OAuthFailedError(ValidationError):
    """Connecting a mailbox with OAuth did not work; `reason` goes back to the settings page."""

    def __init__(self, reason: str) -> None:
        super().__init__('oauth_failed', f'The mailbox could not be connected ({reason})', {'reason': reason})
        self.reason = reason


class InvalidCertificateError(ValidationError):
    """`field` says why: certificate, pkcs12 (file or password), key, key_mismatch, key_type, no_email, not_ca,
    expired, limit."""

    def __init__(self, reason: str) -> None:
        super().__init__('invalid_certificate', f'The certificate cannot be used ({reason})', {'field': reason})


class CertificateNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('certificate_not_found', 'The certificate does not exist')


class CertificateExistsError(ConflictError):
    def __init__(self) -> None:
        super().__init__('certificate_exists', 'This certificate was added already')
