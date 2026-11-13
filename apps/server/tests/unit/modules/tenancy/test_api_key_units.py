import pytest

from zendilohub.core.domain.permissions import PERMISSIONS, permissions_of
from zendilohub.modules.tenancy.domain.exceptions import InvalidApiKeyError
from zendilohub.modules.tenancy.domain.models.api_key import KEY_PERMISSIONS, checked_permissions


def test_keys_get_only_what_owners_may_do_without_a_person() -> None:
    # Owners hold every permission a key can get; admins give what they may do themselves (not `queues.all`).
    assert set(KEY_PERMISSIONS) <= set(permissions_of('owner'))
    assert set(KEY_PERMISSIONS) - set(permissions_of('admin')) == {'queues.all'}
    assert list(KEY_PERMISSIONS) == [permission for permission in PERMISSIONS if permission in KEY_PERMISSIONS]
    assert not {'tenant.manage', 'tenant.delete', 'members.manage', 'members.assign_owner'} & set(KEY_PERMISSIONS)


def test_checks_the_permissions_of_a_key() -> None:
    assert checked_permissions(['audit.view', 'members.view', 'audit.view']) == ('members.view', 'audit.view')
    for wrong in ([], ['tenant.delete'], ['members.view', 'owner']):
        with pytest.raises(InvalidApiKeyError):
            checked_permissions(wrong)
