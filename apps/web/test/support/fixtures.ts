import type { User } from '@/modules/identity/api'
import type { Invitation, Member, OwnTenant, Permission, TenantRole } from '@/modules/tenancy/api'

export function user(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'ada@example.org',
    role: 'user',
    locale: 'en',
    created_at: '2026-10-22T12:00:00Z',
    ...overrides,
  }
}

/** What each role may do; mirrors the server's matrix (apps/server/src/zendilohub/core/domain/permissions.py). */
export const ROLE_PERMISSIONS: Record<TenantRole, Permission[]> = {
  owner: [
    'tenant.manage',
    'tenant.delete',
    'members.view',
    'members.manage',
    'members.assign_owner',
    'queues.manage',
    'queues.all',
    'integrations.manage',
    'audit.view',
  ],
  admin: ['tenant.manage', 'members.view', 'members.manage', 'queues.manage', 'integrations.manage', 'audit.view'],
  manager: ['members.view'],
  agent: ['members.view'],
}

export const TENANT_ID = '00000000-0000-7000-8000-000000000001'

export function tenant(overrides: Partial<OwnTenant> = {}): OwnTenant {
  const role = overrides.role ?? 'owner'
  return {
    id: TENANT_ID,
    name: 'Acme GmbH',
    status: 'active',
    timezone: 'Europe/Berlin',
    locale: 'de',
    created_at: '2026-10-22T12:00:00Z',
    role,
    permissions: ROLE_PERMISSIONS[role],
    ...overrides,
  }
}

export function member(overrides: Partial<Member> = {}): Member {
  return { user_id: 'u1', email: 'ada@example.org', role: 'owner', joined_at: '2026-10-22T12:00:00Z', ...overrides }
}

export function invitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: 'i1',
    email: 'bob@example.org',
    role: 'agent',
    created_at: '2026-10-22T12:00:00Z',
    expires_at: '2026-10-29T12:00:00Z',
    ...overrides,
  }
}

export const ROLE_MATRIX = {
  roles: ['owner', 'admin', 'manager', 'agent'] as TenantRole[],
  permissions: Object.fromEntries(
    ROLE_PERMISSIONS.owner.map((permission) => [
      permission,
      (Object.keys(ROLE_PERMISSIONS) as TenantRole[]).filter((role) => ROLE_PERMISSIONS[role].includes(permission)),
    ]),
  ) as Record<Permission, TenantRole[]>,
}
