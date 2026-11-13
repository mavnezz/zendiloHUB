import {
  BookText,
  Building2,
  Clock,
  ListPlus,
  Timer,
  Workflow,
  Zap,
  FileSignature,
  Filter,
  Mail,
  MailCheck,
  MailX,
  PenLine,
  Contact,
  Inbox,
  Ticket,
  KeyRound,
  LayoutDashboard,
  ScrollText,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
  UsersRound,
} from '@lucide/vue'
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
  key: 'workspace' | 'helpdesk' | 'email' | 'automation' | 'organization'
  items: NavItem[]
}

/** The sidebar of an organization. */
export const navigation: NavGroup[] = [
  {
    key: 'workspace',
    items: [
      { name: 'overview', path: 'overview', icon: LayoutDashboard },
      { name: 'tickets', path: 'tickets', icon: Ticket },
      { name: 'contacts', path: 'contacts', icon: Contact, permission: 'customers.view' },
      { name: 'companies', path: 'companies', icon: Building2, permission: 'customers.view' },
      { name: 'textModules', path: 'text-modules', icon: BookText },
      { name: 'serviceLevels', path: 'service-levels', icon: Timer },
      { name: 'mySignature', path: 'my-signature', icon: PenLine },
    ],
  },
  {
    key: 'helpdesk',
    items: [
      { name: 'queues', path: 'queues', icon: Inbox, permission: 'queues.manage' },
      { name: 'queueGroups', path: 'groups', icon: UsersRound, permission: 'queues.manage' },
      { name: 'queueRights', path: 'queue-rights', icon: UserCog, permission: 'queues.manage' },
      { name: 'ticketFields', path: 'ticket-fields', icon: ListPlus, permission: 'queues.manage' },
    ],
  },
  {
    key: 'email',
    items: [
      { name: 'emailAccounts', path: 'email-accounts', icon: Mail, permission: 'channels.manage' },
      { name: 'queueEmail', path: 'queue-email', icon: MailCheck, permission: 'channels.manage' },
      { name: 'textTemplates', path: 'text-templates', icon: FileSignature, permission: 'channels.manage' },
      { name: 'mailFilters', path: 'mail-filters', icon: Filter, permission: 'channels.manage' },
      { name: 'failedEmails', path: 'failed-emails', icon: MailX, permission: 'channels.manage' },
    ],
  },
  {
    key: 'automation',
    items: [
      { name: 'macros', path: 'macros', icon: Zap, permission: 'automation.manage' },
      { name: 'triggers', path: 'triggers', icon: Workflow, permission: 'automation.manage' },
      { name: 'scheduledJobs', path: 'scheduled-jobs', icon: Clock, permission: 'automation.manage' },
    ],
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

/** Pages below a navigation item. */
const PARENTS: Record<string, string> = {
  ticket: 'tickets',
  newTicket: 'tickets',
  contact: 'contacts',
  company: 'companies',
}

/** The navigation item a page belongs to: its own, or the one it is below. */
export function navItemOf(name: string): string {
  return PARENTS[name] ?? name
}

export function navGroupOf(name: string): NavGroup | undefined {
  const item = navItemOf(name)
  return navigation.find((group) => group.items.some((each) => each.name === item))
}
