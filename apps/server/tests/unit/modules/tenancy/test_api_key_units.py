import pytest

from zendilohub.core.domain.permissions import PERMISSIONS, permissions_of
from zendilohub.modules.tenancy.domain.exceptions import InvalidApiKeyError
from zendilohub.modules.tenancy.domain.models.api_key import KEY_PERMISSIONS, checked_permissions


def test_keys_get_only_what_admins_may_do_without_a_person() -> None:
    # Admins (and owners) create keys: they hold every permission they can give.
    assert set(KEY_PERMISSIONS) <= set(permissions_of('admin'))
    assert list(KEY_PERMISSIONS) == [permission for permission in PERMISSIONS if permission in KEY_PERMISSIONS]
    assert not {'tenant.manage', 'tenant.delete', 'members.manage', 'members.assign_owner'} & set(KEY_PERMISSIONS)


def test_checks_the_permissions_of_a_key() -> None:
    assert checked_permissions(['audit.view', 'members.view', 'audit.view']) == ('members.view', 'audit.view')
    for wrong in ([], ['tenant.delete'], ['members.view', 'owner']):
        with pytest.raises(InvalidApiKeyError):
            checked_permissions(wrong)
