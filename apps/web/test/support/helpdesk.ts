import type { Queue } from '@/modules/access/api'
import type { Contact, Company } from '@/modules/customers/api'
import type { Ticket, TicketDetail, TicketMessage } from '@/modules/tickets/api'

export const FULL = ['view', 'create', 'note', 'reply', 'edit', 'assign', 'move'] as const

export function queue(overrides: Partial<Queue> = {}): Queue {
  return {
    id: 'q1',
    name: 'Support',
    description: '',
    created_at: '2026-11-13T12:00:00Z',
    rights: [...FULL],
    ...overrides,
  }
}

export function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: 't1',
    number: 1001,
    subject: 'Printer broken',
    queue_id: 'q1',
    state: 'open',
    priority: 'normal',
    channel: 'phone',
    customer: {
      id: 'c1',
      name: 'Carl Customer',
      email: 'carl@acme.example',
      phone: null,
      company_id: 'co1',
      company_name: 'Acme',
    },
    owner_id: null,
    responsible_id: null,
    tags: [],
    pending_until: null,
    merged_into_id: null,
    created_at: '2026-11-13T12:00:00Z',
    updated_at: '2026-11-13T12:30:00Z',
    first_response_at: null,
    closed_at: null,
    last_message_at: '2026-11-13T12:00:00Z',
    rights: [...FULL],
    ...overrides,
  }
}

export function detail(overrides: Partial<TicketDetail> = {}): TicketDetail {
  return {
    ...ticket(),
    watchers: [],
    watching: false,
    links: [],
    time_minutes: 0,
    merged_into: null,
    ...overrides,
  }
}

export function message(overrides: Partial<TicketMessage> = {}): TicketMessage {
  return {
    id: 'm1',
    ticket_id: 't1',
    kind: 'public',
    direction: 'in',
    author_kind: 'customer',
    author_id: 'c1',
    author_name: '',
    body: 'It does not print.',
    body_html: null,
    subject: null,
    from_address: null,
    to_addresses: [],
    cc_addresses: [],
    created_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

export function contact(overrides: Partial<Contact> = {}): Contact {
  return {
    id: 'c1',
    name: 'Carl Customer',
    email: 'carl@acme.example',
    phone: '+49 30 1234',
    company: { id: 'co1', name: 'Acme' },
    notes: 'Prefers calls',
    created_at: '2026-11-13T12:00:00Z',
    updated_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

export function company(overrides: Partial<Company> = {}): Company {
  return {
    id: 'co1',
    name: 'Acme',
    domain: 'acme.example',
    notes: '',
    contact_count: 1,
    created_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}
