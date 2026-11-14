import type { User } from '@/modules/identity/api'
import type { BuiltinRole, Invitation, Member, OwnTenant, Permission, Role, Roles } from '@/modules/tenancy/api'

export function user(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'ada@example.org',
    role: 'user',
    locale: 'en',
    two_factor: false,
    created_at: '2026-10-22T12:00:00Z',
    ...overrides,
  }
}

/** What each role may do; mirrors the server's matrix (apps/server/src/zendilohub/core/domain/permissions.py). */
export const ROLE_PERMISSIONS: Record<BuiltinRole, Permission[]> = {
  owner: [
    'tenant.manage',
    'tenant.delete',
    'members.view',
    'members.manage',
    'members.assign_owner',
    'queues.manage',
    'queues.all',
    'tickets.delete',
    'customers.view',
    'customers.manage',
    'channels.manage',
    'automation.manage',
    'knowledge.manage',
    'service.manage',
    'reports.view',
    'integrations.manage',
    'audit.view',
  ],
  admin: [
    'tenant.manage',
    'members.view',
    'members.manage',
    'queues.manage',
    'tickets.delete',
    'customers.view',
    'customers.manage',
    'channels.manage',
    'automation.manage',
    'knowledge.manage',
    'service.manage',
    'reports.view',
    'integrations.manage',
    'audit.view',
  ],
  manager: ['members.view', 'customers.view', 'customers.manage', 'knowledge.manage', 'reports.view'],
  agent: ['members.view', 'customers.view', 'customers.manage'],
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
    role_name: null,
    permissions: ROLE_PERMISSIONS[role as BuiltinRole] ?? [],
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

export const OWNER_ONLY: Permission[] = ['tenant.delete', 'members.assign_owner']

export function role(overrides: Partial<Role> = {}): Role {
  return {
    id: 'r1',
    name: 'Team lead',
    description: 'Runs a team',
    builtin: false,
    permissions: ['members.view', 'queues.manage'],
    member_count: 0,
    ...overrides,
  }
}

/** The roles of an organization as the server lists them: built-in first, then `own`. */
export function roles(own: Role[] = [], members: Partial<Record<string, number>> = { owner: 1 }): Roles {
  return {
    permissions: ROLE_PERMISSIONS.owner,
    owner_only: OWNER_ONLY,
    roles: [
      ...(Object.keys(ROLE_PERMISSIONS) as BuiltinRole[]).map((id) => ({
        id,
        name: null,
        description: '',
        builtin: true,
        permissions: ROLE_PERMISSIONS[id],
        member_count: members[id] ?? 0,
      })),
      ...own,
    ],
  }
}
