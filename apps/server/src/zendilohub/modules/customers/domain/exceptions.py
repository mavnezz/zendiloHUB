from zendilohub.core.domain.app_domain_error import ConflictError, NotFoundError, ValidationError


class InvalidContactError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_contact', f'Please check the contact ({field})', {'field': field})


class InvalidCompanyError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_company', f'Please check the company ({field})', {'field': field})


class ContactNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('contact_not_found', 'The contact does not exist')


class CompanyNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('company_not_found', 'The company does not exist')


class ContactEmailTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('contact_email_taken', 'There is already a contact with this e-mail address')


class CompanyNameTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('company_name_taken', 'There is already a company of this name')


class CompanyDomainTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('company_domain_taken', 'Another company has this domain already')


class ContactHasTicketsError(ConflictError):
    def __init__(self, count: int) -> None:
        super().__init__('contact_has_tickets', 'The contact still has tickets', {'count': count})
