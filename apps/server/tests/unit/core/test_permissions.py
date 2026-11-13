from itertools import pairwise

from zendilohub.core.domain.permissions import BUILTIN_ROLES, PERMISSIONS, allows, is_builtin, ordered, permissions_of


def test_owners_may_do_everything() -> None:
    assert permissions_of('owner') == list(PERMISSIONS)


def test_roles_are_ordered_by_what_they_may_do() -> None:
    allowed = [set(permissions_of(role)) for role in BUILTIN_ROLES]
    assert all(lower <= higher for higher, lower in pairwise(allowed))


def test_checks_single_permissions() -> None:
    assert allows('admin', 'members.manage')
    assert not allows('admin', 'tenant.delete')
    assert allows('manager', 'members.view')
    assert not allows('manager', 'audit.view')


def test_tells_built_in_roles_from_own_ones() -> None:
    assert is_builtin('agent')
    assert not is_builtin('0196f3c0-0000-7000-8000-000000000001')
    assert ordered({'audit.view', 'tenant.manage'}) == ['tenant.manage', 'audit.view']
