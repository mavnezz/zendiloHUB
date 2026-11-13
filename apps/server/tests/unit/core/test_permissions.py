from itertools import pairwise

from zendilohub.core.domain.permissions import PERMISSIONS, TENANT_ROLES, allows, permissions_of


def test_owners_may_do_everything() -> None:
    assert permissions_of('owner') == list(PERMISSIONS)


def test_roles_are_ordered_by_what_they_may_do() -> None:
    allowed = [set(permissions_of(role)) for role in TENANT_ROLES]
    assert all(lower <= higher for higher, lower in pairwise(allowed))


def test_checks_single_permissions() -> None:
    assert allows('admin', 'members.manage')
    assert not allows('admin', 'tenant.delete')
    assert allows('manager', 'members.view')
    assert not allows('manager', 'audit.view')
