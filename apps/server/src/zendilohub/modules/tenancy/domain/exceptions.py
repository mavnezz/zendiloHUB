from zendilohub.core.domain.app_domain_error import ConflictError, ForbiddenError, NotFoundError, ValidationError


class InvalidTenantNameError(ValidationError):
    def __init__(self, max_length: int) -> None:
        super().__init__(
            'invalid_tenant_name',
            f'The name must have between 1 and {max_length} characters',
            {'max_length': max_length},
        )


class InvalidTimezoneError(ValidationError):
    def __init__(self) -> None:
        super().__init__('invalid_timezone', 'This is not a known time zone')


class InvalidEmailError(ValidationError):
    def __init__(self) -> None:
        super().__init__('invalid_email', 'This is not a valid e-mail address')


class TenantNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('tenant_not_found', 'The organization does not exist')


class MemberNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('member_not_found', 'This person is no member of the organization')


class AlreadyMemberError(ConflictError):
    def __init__(self) -> None:
        super().__init__('already_member', 'This person is already a member of the organization')


class LastOwnerError(ConflictError):
    def __init__(self) -> None:
        super().__init__('last_owner', 'An organization needs at least one owner')


class InvalidInvitationError(ValidationError):
    """Unknown, revoked, accepted or expired."""

    def __init__(self) -> None:
        super().__init__('invalid_invitation', 'This invitation is invalid or has expired')


class InvitationForOtherEmailError(ForbiddenError):
    def __init__(self, email: str) -> None:
        super().__init__(
            'invitation_for_other_email',
            'This invitation was sent to another e-mail address; log in with that address to accept it',
            {'email': email},
        )


class InvitationNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('invitation_not_found', 'The invitation does not exist')


class OwnerOnlyError(ForbiddenError):
    """Only owners may make someone an owner or change an owner's role."""

    def __init__(self) -> None:
        super().__init__('permission_denied', 'Only owners may do this', {'permission': 'members.assign_owner'})


class InvalidApiKeyError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_api_key', f'Please check the API key ({field})', {'field': field})


class ApiKeyNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('api_key_not_found', 'The API key does not exist')


class ApiKeyLimitError(ConflictError):
    def __init__(self, limit: int) -> None:
        super().__init__('api_key_limit', f'An organization can have at most {limit} API keys', {'limit': limit})


class SingleOrganizationError(ForbiddenError):
    """A self-hosted instance has exactly one organization (the setup wizard makes it)."""

    def __init__(self) -> None:
        super().__init__('single_organization', 'This instance has its organization already')


class InvalidRoleError(ValidationError):
    def __init__(self, field: str) -> None:
        super().__init__('invalid_role', f'Please check the role ({field})', {'field': field})


class RoleNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__('role_not_found', 'The role does not exist')


class RoleNameTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__('role_name_taken', 'There is already a role of this name')


class RoleLimitError(ConflictError):
    def __init__(self, limit: int) -> None:
        super().__init__('role_limit', f'An organization can have at most {limit} roles of its own', {'limit': limit})


class RoleInUseError(ConflictError):
    def __init__(self) -> None:
        super().__init__('role_in_use', 'Members or invitations still have this role; give them another one first')


class RoleExceedsOwnError(ForbiddenError):
    """Nobody hands out (or takes away) more than they may do themselves."""

    def __init__(self) -> None:
        super().__init__('role_exceeds_own', 'This role may do things you may not do yourself')
