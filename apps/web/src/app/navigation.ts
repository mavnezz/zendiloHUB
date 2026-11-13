import { KeyRound, LayoutDashboard, ScrollText, Settings, ShieldCheck, Users } from '@lucide/vue'
import type { Component } from 'vue'
import type { Permission } from '@/modules/tenancy/api'

export interface NavItem {
  /** Route name and message key (`nav.<key>`). */
  name: string
  path: string
  icon: Component
  /** Hidden from roles without it. */
  permission?: Permission
}

export interface NavGroup {
  key: 'workspace' | 'organization'
  items: NavItem[]
}

/** The sidebar of an organization; queues and tickets join with phases 1 and 2 (docs/PLAN.md). */
export const navigation: NavGroup[] = [
  {
    key: 'workspace',
    items: [{ name: 'overview', path: 'overview', icon: LayoutDashboard }],
  },
  {
    key: 'organization',
    items: [
      { name: 'team', path: 'team', icon: Users, permission: 'members.view' },
      { name: 'roles', path: 'roles', icon: ShieldCheck },
      { name: 'settings', path: 'settings', icon: Settings, permission: 'tenant.manage' },
      { name: 'apiKeys', path: 'api-keys', icon: KeyRound, permission: 'integrations.manage' },
      { name: 'audit', path: 'audit-log', icon: ScrollText, permission: 'audit.view' },
    ],
  },
]

/** Pages below a navigation item (none yet; a ticket will belong to its queue). */
const PARENTS: Record<string, string> = {}

/** The navigation item a page belongs to: its own, or the one it is below. */
export function navItemOf(name: string): string {
  return PARENTS[name] ?? name
}

export function navGroupOf(name: string): NavGroup | undefined {
  const item = navItemOf(name)
  return navigation.find((group) => group.items.some((each) => each.name === item))
}
