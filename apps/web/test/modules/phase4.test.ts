import { describe, expect, it } from 'vitest'
import type { Rule } from '@/modules/automation/api'
import RulesView from '@/modules/automation/views/RulesView.vue'
import TextModulesView from '@/modules/knowledge/views/TextModulesView.vue'
import NotificationBell from '@/modules/notifications/components/NotificationBell.vue'
import ServiceLevelsView from '@/modules/service/views/ServiceLevelsView.vue'
import { useSession } from '@/modules/identity/session'
import type { TenantRole } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import TicketFieldsView from '@/modules/tickets/views/TicketFieldsView.vue'
import TicketsView from '@/modules/tickets/views/TicketsView.vue'
import TicketView from '@/modules/tickets/views/TicketView.vue'
import { FakeApi } from '../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../support/fixtures'
import { detail, message, queue, ticket } from '../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, testRouter, text, type } from '../support/mount'
import { spyToasts } from '../support/toasts'

const BASE = `/tenants/${TENANT_ID}`

function inTenant(role: TenantRole = 'owner'): void {
  useSession().start(user())
  useTenants().put(tenant({ role }))
  useTenants().select(TENANT_ID)
}

function rule(overrides: Partial<Rule> = {}): Rule {
  return {
    id: 'r1',
    kind: 'macro',
    name: 'Close as solved',
    active: true,
    position: 1,
    actions: {
      state: 'closed',
      pending_hours: null,
      priority: null,
      queue_id: null,
      owner_id: null,
      owner_me: true,
      unassign: false,
      add_tags: ['solved'],
      remove_tags: ['open'],
      note: 'Solved.',
      reply: '',
    },
    event: null,
    conditions: [],
    schedule: null,
    last_run_at: null,
    ...overrides,
  }
}

async function mountRules(kind: Rule['kind'], path: string) {
  const router = testRouter()
  router.addRoute({ path: `/t/:tenantId/rules/${path}`, name: `rules-${kind}`, component: RulesView, meta: { kind } })
  return mountView(RulesView, { router, path: `/t/${TENANT_ID}/rules/${path}` })
}

describe('RulesView', () => {
  it('creates, edits and deletes macros', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/macros`, [
        rule(),
        rule({
          id: 'r2',
          name: 'Off',
          active: false,
          actions: { ...rule().actions, owner_me: false, unassign: true, note: '' },
        }),
      ])
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member()])
      .json('POST', `${BASE}/macros`, rule({ id: 'r3', name: 'Wait' }), 201)
      .json('PATCH', `${BASE}/macros/r1`, rule())
      .on('DELETE', `${BASE}/macros/r1`, { status: 204 })
    await mountRules('macro', 'macros')
    expect($('[data-test="rule-Close as solved"]').text().replace(/\s+/g, ' ')).toContain(
      'State: Closed · Take it (whoever applies it) · +#solved · −#open · with a note',
    )
    expect($('[data-test=rule-Off]').text()).toContain('off')

    await click('[data-test=create-rule]')
    await type('#rule-name', 'Wait')
    await $('#action-state').setValue('pending_reminder')
    await type('#action-pending', '48')
    await $('#action-priority').setValue('low')
    await $('#action-queue').setValue('q1')
    await $('#action-owner').setValue('me')
    await type('#action-add-tags', 'waiting, customer')
    await type('#action-note', 'Asked the customer')
    expect(exists('#action-reply')).toBe(false)
    await click('[data-test=save-rule]')
    expect(fake.last('POST', `${BASE}/macros`)?.body).toEqual({
      name: 'Wait',
      active: true,
      conditions: [],
      actions: {
        state: 'pending_reminder',
        pending_hours: 48,
        priority: 'low',
        queue_id: 'q1',
        owner_id: null,
        owner_me: true,
        unassign: false,
        add_tags: ['waiting', 'customer'],
        remove_tags: [],
        note: 'Asked the customer',
        reply: '',
      },
    })
    expect(toasts.success()).toContain('"Wait" saved.')

    await click('[data-test="edit-rule-Close as solved"]')
    expect(($('#action-owner').element as HTMLSelectElement).value).toBe('me')
    await click('[data-test=save-rule]')
    expect(fake.last('PATCH', `${BASE}/macros/r1`)?.body).toMatchObject({
      actions: { owner_me: true, remove_tags: ['open'] },
    })

    await click('[data-test="delete-rule-Close as solved"]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/macros/r1`)).toHaveLength(1)
  })

  it('sets up triggers with conditions', async () => {
    inTenant()
    const trigger = rule({
      id: 't1',
      kind: 'trigger',
      name: 'Invoices',
      event: 'created',
      conditions: [{ field: 'queue_id', operator: 'is', value: 'q1' }],
      actions: { ...rule().actions, owner_me: false, owner_id: 'u1', reply: 'We got it', note: '' },
    })
    const fake = new FakeApi()
      .json('GET', `${BASE}/triggers`, [trigger])
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member()])
      .on('POST', `${BASE}/triggers`, (request) => ({ status: 201, body: { ...trigger, ...(request.body as object) } }))
      .error('PATCH', `${BASE}/triggers/t1`, 422, 'invalid_rule')
    await mountRules('trigger', 'triggers')
    expect($('[data-test=rule-Invoices]').text()).toContain('Ticket created')
    expect($('[data-test=rule-Invoices]').text()).toContain('with a message to the customer')

    await click('[data-test=create-rule]')
    await type('#rule-name', 'VIP')
    await $('#rule-event').setValue('customer_replied')
    await click('[data-test=add-rule-condition]')
    await $('[data-test=rule-condition-0] input[aria-label=Value]').setValue('@vip.example')
    await click('[data-test=add-rule-condition]')
    await $('[data-test=rule-condition-1] select[aria-label=Field]').setValue('owner')
    await $('[data-test=rule-condition-1] select[aria-label=Comparison]').setValue('is_not_set')
    await $('#action-owner').setValue('u1')
    await type('#action-reply', 'Thanks!')
    await click('[data-test=save-rule]')
    expect(fake.last('POST', `${BASE}/triggers`)?.body).toMatchObject({
      event: 'customer_replied',
      conditions: [
        { field: 'subject', operator: 'contains', value: '@vip.example' },
        { field: 'owner', operator: 'is_not_set', value: '' },
      ],
      actions: { owner_id: 'u1', reply: 'Thanks!' },
    })

    await click('[data-test=edit-rule-Invoices]')
    await click('[data-test=save-rule]')
    expect(text()).toContain('Please check the rule')
  })

  it('sets up scheduled jobs', async () => {
    inTenant()
    const jobs = new FakeApi()
      .json('GET', `${BASE}/scheduled-jobs`, [
        rule({
          id: 's1',
          kind: 'schedule',
          name: 'Close stale',
          last_run_at: '2026-11-13T12:00:00Z',
          schedule: {
            states: ['pending_reminder'],
            queue_ids: ['q1'],
            priorities: [],
            tags: [],
            owner: 'any',
            idle_hours: 72,
            age_hours: null,
            pending_passed: false,
          },
        }),
      ])
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [])
      .json('POST', `${BASE}/scheduled-jobs`, rule({ id: 's2', kind: 'schedule' }), 201)
    await mountRules('schedule', 'scheduled-jobs')
    expect($('[data-test="rule-Close stale"]').text()).toContain('last run')
    await click('[data-test=create-rule]')
    await type('#rule-name', 'Remind')
    await click('[data-test=schedule-state-open] button')
    await type('#schedule-idle', '24')
    await click('[data-test=schedule-pending]')
    await $('#action-priority').setValue('high')
    await click('[data-test=save-rule]')
    expect(jobs.last('POST', `${BASE}/scheduled-jobs`)?.body).toMatchObject({
      schedule: { states: ['open'], idle_hours: 24, pending_passed: true, owner: 'any' },
      actions: { priority: 'high' },
    })
  })

  it('says when there are no jobs', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/scheduled-jobs`, [])
      .json('GET', `${BASE}/queues`, [])
      .json('GET', `${BASE}/members`, [])
    await mountRules('schedule', 'scheduled-jobs')
    expect(text()).toContain('No scheduled jobs yet')
  })
})

describe('TextModulesView, TicketFieldsView and ServiceLevelsView', () => {
  it('manages text modules', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/text-modules`, [
        {
          id: 'm1',
          name: 'Thanks',
          keyword: 'thanks',
          body: 'Thank you!',
          queue_ids: [],
          updated_at: '2026-11-13T12:00:00Z',
        },
        {
          id: 'm2',
          name: 'IBAN',
          keyword: 'iban',
          body: 'DE00',
          queue_ids: ['q1'],
          updated_at: '2026-11-13T12:00:00Z',
        },
      ])
      .json('GET', `${BASE}/queues`, [queue()])
      .on('POST', `${BASE}/text-modules`, (request) => ({
        status: 201,
        body: { id: 'm3', ...(request.body as object) },
      }))
      .on('PATCH', `${BASE}/text-modules/m1`, (request) => ({ body: { id: 'm1', ...(request.body as object) } }))
      .on('DELETE', `${BASE}/text-modules/m1`, { status: 204 })
    await mountView(TextModulesView, { path: `/t/${TENANT_ID}/text-modules` })
    expect($('[data-test=module-thanks]').text()).toContain('every queue')
    expect($('[data-test=module-iban]').text()).toContain('Support')

    await click('[data-test=create-module]')
    await type('#module-name', 'Größe ändern')
    expect(($('#module-keyword').element as HTMLInputElement).value).toBe('gro-e-andern')
    await type('#module-keyword', 'size')
    await type('#module-body', 'Hello {{customer.name}}')
    await click('[data-test=module-queue-q1] button')
    await click('[data-test=save-module]')
    expect(fake.last('POST', `${BASE}/text-modules`)?.body).toEqual({
      name: 'Größe ändern',
      keyword: 'size',
      body: 'Hello {{customer.name}}',
      queue_ids: ['q1'],
    })
    expect(toasts.success()).toContain('::size saved.')

    await click('[data-test=edit-module-thanks]')
    await type('#module-name', 'Thank you')
    await click('[data-test=save-module]')
    expect(fake.last('PATCH', `${BASE}/text-modules/m1`)?.body).toMatchObject({ keyword: 'thanks', name: 'Thank you' })
    await click('[data-test=delete-module-thanks]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/text-modules/m1`)).toHaveLength(1)

    fake.error('POST', `${BASE}/text-modules`, 409, 'keyword_taken')
    await click('[data-test=create-module]')
    await type('#module-name', 'X')
    await type('#module-body', 'x')
    await click('[data-test=save-module]')
    expect(text()).toContain('Another text module has this keyword.')
  })

  it('shows text modules to agents without controls', async () => {
    inTenant('agent')
    new FakeApi().json('GET', `${BASE}/text-modules`, []).json('GET', `${BASE}/queues`, [])
    await mountView(TextModulesView, { path: `/t/${TENANT_ID}/text-modules` })
    expect(text()).toContain('No text modules yet')
    expect(exists('[data-test=create-module]')).toBe(false)
  })

  it('manages ticket fields', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/ticket-fields`, [
        { id: 'f1', key: 'product', label: 'Product', kind: 'select', options: ['Printer'], position: 1 },
      ])
      .on('POST', `${BASE}/ticket-fields`, (request) => ({
        status: 201,
        body: { id: 'f2', position: 2, ...(request.body as object) },
      }))
      .on('PATCH', `${BASE}/ticket-fields/f1`, (request) => ({
        body: { id: 'f1', position: 1, ...(request.body as object) },
      }))
      .on('DELETE', `${BASE}/ticket-fields/f1`, { status: 204 })
    await mountView(TicketFieldsView, { path: `/t/${TENANT_ID}/ticket-fields` })
    expect($('[data-test=field-product]').text().replace(/\s+/g, ' ')).toContain('Choice · Printer')

    await click('[data-test=create-field]')
    await type('#field-label', 'Contract no.')
    await $('#field-label').trigger('blur')
    expect(($('#field-key').element as HTMLInputElement).value).toBe('contract_no')
    await click('[data-test=save-field]')
    expect(fake.last('POST', `${BASE}/ticket-fields`)?.body).toEqual({
      key: 'contract_no',
      label: 'Contract no.',
      kind: 'text',
      options: [],
    })

    await click('[data-test=edit-field-product]')
    expect(($('#field-key').element as HTMLInputElement).disabled).toBe(true)
    await type('#field-options', 'Printer\nScanner\n')
    await click('[data-test=save-field]')
    expect(fake.last('PATCH', `${BASE}/ticket-fields/f1`)?.body).toMatchObject({ options: ['Printer', 'Scanner'] })
    await click('[data-test=delete-field-product]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/ticket-fields/f1`)).toHaveLength(1)

    fake.error('POST', `${BASE}/ticket-fields`, 409, 'field_key_taken')
    await click('[data-test=create-field]')
    await type('#field-label', 'Product')
    await type('#field-key', 'product')
    await click('[data-test=save-field]')
    expect(text()).toContain('There is already a field with this key.')
  })

  it('manages service levels and business hours', async () => {
    const toasts = spyToasts()
    inTenant()
    const calendar = {
      id: 'c1',
      name: 'Office',
      timezone: 'Europe/Berlin',
      hours: { mon: [['08:00', '17:00']] as [string, string][] },
      holidays: ['2026-12-24'],
    }
    const fake = new FakeApi()
      .json('GET', `${BASE}/service-levels`, {
        calendars: [calendar],
        policies: [
          {
            id: 'p1',
            name: 'Urgent',
            position: 1,
            active: true,
            queue_ids: [],
            priorities: ['urgent'],
            first_response_minutes: 30,
            solution_minutes: 240,
            calendar_id: null,
          },
          {
            id: 'p2',
            name: 'Normal',
            position: 2,
            active: false,
            queue_ids: ['q1'],
            priorities: [],
            first_response_minutes: 480,
            solution_minutes: null,
            calendar_id: 'c1',
          },
        ],
      })
      .json('GET', `${BASE}/queues`, [queue()])
      .on('POST', `${BASE}/service-policies`, (request) => ({
        status: 201,
        body: { id: 'p3', ...(request.body as object) },
      }))
      .on('PATCH', `${BASE}/service-policies/p1`, (request) => ({ body: { id: 'p1', ...(request.body as object) } }))
      .on('POST', `${BASE}/service-calendars`, (request) => ({
        status: 201,
        body: { id: 'c2', ...(request.body as object) },
      }))
      .on('PATCH', `${BASE}/service-calendars/c1`, (request) => ({ body: { id: 'c1', ...(request.body as object) } }))
      .on('DELETE', `${BASE}/service-calendars/c1`, { status: 204 })
      .on('DELETE', `${BASE}/service-policies/p2`, { status: 204 })
    await mountView(ServiceLevelsView, { path: `/t/${TENANT_ID}/service-levels` })
    expect($('[data-test=policy-Urgent]').text().replace(/\s+/g, ' ')).toContain(
      'all queues · Urgent · First response: 30 min · Solution: 4 h · around the clock',
    )
    expect($('[data-test=policy-Normal]').text()).toContain('Support · all priorities')
    expect($('[data-test=policy-Normal]').text()).toContain('Office')
    expect($('[data-test=calendar-Office]').text().replace(/\s+/g, ' ')).toContain('Mon 08:00–17:00 · 1 holiday')

    await click('[data-test=create-policy]')
    await type('#policy-name', 'High')
    await click('[data-test=policy-priority-high] button')
    await type('#policy-first', '60')
    await $('#policy-calendar').setValue('c1')
    await click('[data-test=save-policy]')
    expect(fake.last('POST', `${BASE}/service-policies`)?.body).toEqual({
      name: 'High',
      active: true,
      queue_ids: [],
      priorities: ['high'],
      first_response_minutes: 60,
      solution_minutes: null,
      calendar_id: 'c1',
    })
    expect(toasts.success()).toContain('"High" saved.')
    await click('[data-test=edit-policy-Urgent]')
    await click('[data-test=save-policy]')
    expect(fake.last('PATCH', `${BASE}/service-policies/p1`)?.body).toMatchObject({ priorities: ['urgent'] })

    await click('[data-test=create-calendar]')
    expect(($('#calendar-mon').element as HTMLInputElement).value).toBe('08:00-17:00')
    expect(($('#calendar-sat').element as HTMLInputElement).value).toBe('')
    await type('#calendar-name', 'Shop')
    await type('#calendar-sat', '10:00-14:00')
    await type('#calendar-holidays', '2026-12-25\n2026-12-26')
    await click('[data-test=save-calendar]')
    const body = fake.last('POST', `${BASE}/service-calendars`)?.body as {
      hours: Record<string, string[][]>
      holidays: string[]
    }
    expect(body.hours.sat).toEqual([['10:00', '14:00']])
    expect(body.holidays).toEqual(['2026-12-25', '2026-12-26'])
    await click('[data-test=edit-calendar-Office]')
    await click('[data-test=save-calendar]')
    expect(fake.last('PATCH', `${BASE}/service-calendars/c1`)?.body).toMatchObject({ holidays: ['2026-12-24'] })

    await click('[data-test=delete-calendar-Office]')
    expect(text()).toContain('count around the clock')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/service-calendars/c1`)).toHaveLength(1)
    await click('[data-test=delete-policy-Normal]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/service-policies/p2`)).toHaveLength(1)

    fake.error('POST', `${BASE}/service-policies`, 422, 'invalid_service')
    await click('[data-test=create-policy]')
    await type('#policy-name', 'X')
    await click('[data-test=save-policy]')
    expect(text()).toContain('Please check the service level')
    fake.error('POST', `${BASE}/service-calendars`, 422, 'invalid_service')
    await click('[data-test=create-calendar]')
    await type('#calendar-name', 'Y')
    await click('[data-test=save-calendar]')
    expect($$('[role=dialog] [data-test=error]').length).toBeGreaterThan(0)
  })
})

describe('ServiceLevelsView for others', () => {
  it('shows agents the service levels without controls, and failures', async () => {
    inTenant('agent')
    new FakeApi()
      .json('GET', `${BASE}/service-levels`, { calendars: [], policies: [] })
      .json('GET', `${BASE}/queues`, [])
    await mountView(ServiceLevelsView, { path: `/t/${TENANT_ID}/service-levels` })
    expect(exists('[data-test=create-policy]')).toBe(false)
    expect(text()).toContain('None yet.')

    new FakeApi().error('GET', `${BASE}/service-levels`, 500, 'internal_error').json('GET', `${BASE}/queues`, [])
    await mountView(ServiceLevelsView, { path: `/t/${TENANT_ID}/service-levels` })
    expect(exists('[data-test=error]')).toBe(true)
  })

  it('unticks a priority before saving', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/service-levels`, { calendars: [], policies: [] })
      .json('GET', `${BASE}/queues`, [queue()])
      .on('POST', `${BASE}/service-policies`, (request) => ({
        status: 201,
        body: { id: 'p9', ...(request.body as object) },
      }))
    await mountView(ServiceLevelsView, { path: `/t/${TENANT_ID}/service-levels` })
    await click('[data-test=create-policy]')
    await type('#policy-name', 'All')
    await click('[data-test=policy-priority-low] button')
    await click('[data-test=policy-priority-low] button')
    await type('#policy-solution', '600')
    await click('[data-test=save-policy]')
    expect(fake.last('POST', `${BASE}/service-policies`)?.body).toMatchObject({ priorities: [], solution_minutes: 600 })
  })
})

describe('NotificationBell', () => {
  it('shows what is new, marks it read and turns e-mails on', async () => {
    inTenant()
    const items = [
      {
        id: 'n1',
        kind: 'assigned',
        ticket_id: 't1',
        ticket_number: 1001,
        subject: 'Printer broken',
        actor: 'bob@example.org',
        created_at: '2026-11-13T12:00:00Z',
        read_at: null,
      },
      {
        id: 'n2',
        kind: 'sla_breached',
        ticket_id: 't2',
        ticket_number: 1002,
        subject: 'Server down',
        actor: 'zendiloHUB',
        created_at: '2026-11-13T11:00:00Z',
        read_at: '2026-11-13T11:30:00Z',
      },
    ]
    const fake = new FakeApi()
      .json('GET', `${BASE}/notifications`, { items, unread: 1 })
      .json('GET', `${BASE}/me/notification-settings`, { email: false })
      .on('PUT', `${BASE}/me/notification-settings`, (request) => ({ body: request.body }))
      .on('POST', `${BASE}/notifications/read`, () => ({ body: { items, unread: 0 } }))
    const { router } = await mountView(NotificationBell, { path: `/t/${TENANT_ID}/overview` })
    expect($('[data-test=unread]').text()).toBe('1')

    await click('[data-test=bell]')
    expect(text()).toContain('bob@example.org gave it to you')
    expect(text()).toContain('Service level missed')
    await click('[data-test=email-notifications]')
    expect(fake.last('PUT', `${BASE}/me/notification-settings`)?.body).toEqual({ email: true })
    await click('[data-test=notification-n1]')
    expect(fake.last('POST', `${BASE}/notifications/read`)?.body).toEqual({ ids: ['n1'] })
    expect(router.currentRoute.value.params.ticketId).toBe('t1')
  })

  it('marks everything read and copes with failures', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/notifications`, {
        items: [],
        unread: 120,
      })
      .json('GET', `${BASE}/me/notification-settings`, { email: true })
      .on('POST', `${BASE}/notifications/read`, { body: { items: [], unread: 0 } })
      .error('PUT', `${BASE}/me/notification-settings`, 500, 'internal_error')
    await mountView(NotificationBell, { path: `/t/${TENANT_ID}/overview` })
    expect($('[data-test=unread]').text()).toBe('99+')
    await click('[data-test=bell]')
    expect(text()).toContain('Nothing new.')
    await click('[data-test=read-all]')
    expect(fake.last('POST', `${BASE}/notifications/read`)?.body).toEqual({})
    expect(exists('[data-test=unread]')).toBe(false)
    const toasts = spyToasts()
    await click('[data-test=email-notifications]')
    expect(toasts.error()).toHaveLength(1)
  })
})

describe('Tickets with phase 4', () => {
  function api(shown = detail()): FakeApi {
    return new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member(), member({ user_id: 'u2', email: 'bob@example.org', role: 'agent' })])
      .json('GET', `${BASE}/tickets/t1`, shown)
      .json('GET', `${BASE}/tickets/t1/messages`, [message()])
      .json('GET', `${BASE}/tickets/t1/history`, [])
      .json('GET', `${BASE}/queues/q1/assignees`, ['u1'])
      .json('GET', `${BASE}/ticket-fields`, [
        { id: 'f1', key: 'product', label: 'Product', kind: 'select', options: ['Printer'], position: 1 },
        { id: 'f2', key: 'warranty', label: 'Warranty', kind: 'checkbox', options: [], position: 2 },
        { id: 'f3', key: 'amount', label: 'Amount', kind: 'number', options: [], position: 3 },
      ])
      .json('GET', `${BASE}/tickets/t1/checklist`, [{ id: 'i1', text: 'Check toner', done: false, position: 1 }])
      .json('GET', `${BASE}/tickets/t1/service-level`, {
        ticket_id: 't1',
        policy_id: 'p1',
        first_response_due: '2026-11-13T12:30:00Z',
        solution_due: '2099-01-01T00:00:00Z',
        first_responded_at: null,
        solved_at: null,
        breached: ['first_response'],
      })
      .json('PUT', `${BASE}/tickets/t1/presence`, [{ user_id: 'u2', writing: true }])
      .json('GET', `${BASE}/macros`, [rule()])
      .json('GET', `${BASE}/text-modules`, [
        {
          id: 'm1',
          name: 'Thanks',
          keyword: 'thanks',
          body: 'Thanks, {{customer.name}}!',
          queue_ids: [],
          updated_at: '',
        },
      ])
      .on('PATCH', `${BASE}/tickets/t1`, (request) => ({ body: { ...shown, ...(request.body as object) } }))
      .json('POST', `${BASE}/tickets/t1/messages`, message(), 201)
      .json('POST', `${BASE}/tickets/t1/checklist`, { id: 'i2', text: 'Order', done: false, position: 2 }, 201)
      .json('PATCH', `${BASE}/tickets/t1/checklist/i1`, { id: 'i1', text: 'Check toner', done: true, position: 1 })
      .on('DELETE', `${BASE}/tickets/t1/checklist/i1`, { status: 204 })
  }

  it('shows deadlines, fields, the checklist and who else is there', async () => {
    inTenant()
    const fake = api(detail({ fields: { product: 'Printer' }, tags: ['open'] }))
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=sla-firstResponse]').text()).toContain('missed')
    expect($('[data-test=sla-solution]').text()).not.toContain('missed')
    expect($('[data-test=viewers]').text()).toContain('bob@example.org is writing')
    expect(($('#custom-product').element as HTMLSelectElement).value).toBe('Printer')
    expect($('[data-test=checklist-progress]').text()).toBe('0/1')

    await $('#custom-product').setValue('')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ fields: { product: null } })
    await click('[data-test=custom-warranty] button')
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ fields: { warranty: true } })
    await $('#custom-amount').setValue('12')
    await $('#custom-amount').trigger('change')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ fields: { amount: 12 } })

    await click('[data-test=item-i1] button')
    expect(fake.last('PATCH', `${BASE}/tickets/t1/checklist/i1`)?.body).toEqual({ done: true })
    await type('[data-test=new-item]', 'Order')
    $('[data-test=new-item]').element.closest('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()
    expect(fake.last('POST', `${BASE}/tickets/t1/checklist`)?.body).toEqual({ text: 'Order' })
    await click('[data-test=remove-item-i1]')
    expect(fake.calls('DELETE', `${BASE}/tickets/t1/checklist/i1`)).toHaveLength(1)

    // Writing tells the others.
    await click('[data-test=option-note]')
    await type('[data-test=composer-body]', 'Hm')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/tickets/t1/presence`)?.body).toEqual({ writing: true })
  })

  it('applies macros and inserts text modules', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api(detail({ tags: ['open', 'printer'] }))
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })

    await click('[data-test=macros]')
    await click('[data-test="macro-Close as solved"]')
    expect(fake.last('POST', `${BASE}/tickets/t1/messages`)?.body).toEqual({
      kind: 'internal',
      body: 'Solved.',
      direction: 'out',
    })
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({
      state: 'closed',
      owner_id: 'u1',
      tags: ['printer', 'solved'],
    })
    expect(toasts.success()).toContain('Macro "Close as solved" applied.')

    await click('[data-test=option-note]')
    await type('[data-test=composer-body]', 'See ::tha')
    expect($('[data-test=suggestions]').text()).toContain('::thanks')
    await click('[data-test=suggest-thanks]')
    expect(($('[data-test=composer-body]').element as HTMLTextAreaElement).value).toBe('See Thanks, Carl Customer!')
  })

  it('applies macros that wait, move or unassign, and reports refusals', async () => {
    const toasts = spyToasts()
    inTenant()
    const waiting = rule({
      id: 'r2',
      name: 'Wait',
      actions: {
        ...rule().actions,
        state: 'pending_reminder',
        pending_hours: 2,
        priority: 'low',
        queue_id: 'q2',
        owner_me: false,
        unassign: true,
        add_tags: [],
        remove_tags: [],
        note: '',
      },
    })
    const fake = api()
      .json('GET', `${BASE}/macros`, [waiting])
      .error('PATCH', `${BASE}/tickets/t1`, 403, 'queue_right_missing')
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    await click('[data-test=macros]')
    await click('[data-test=macro-Wait]')
    const body = fake.last('PATCH', `${BASE}/tickets/t1`)?.body as Record<string, unknown>
    expect(body).toMatchObject({ state: 'pending_reminder', priority: 'low', queue_id: 'q2', owner_id: null })
    expect(new Date(String(body.pending_until)).getTime()).toBeGreaterThan(Date.now())
    expect(toasts.error()).toHaveLength(1)
  })

  it('describes every action of a rule', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/macros`, [
        rule({
          actions: {
            ...rule().actions,
            state: null,
            owner_me: false,
            priority: 'urgent',
            queue_id: 'q1',
            add_tags: [],
            remove_tags: [],
            note: '',
          },
        }),
      ])
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [])
    await mountRules('macro', 'macros')
    expect($('[data-test="rule-Close as solved"]').text()).toContain('Priority: Urgent · Move to Support')
  })

  it('lets API keys look without being counted, and waits a day by default', async () => {
    inTenant()
    useTenants().put(tenant({ role: null, permissions: ['queues.all'] }))
    const note = rule({
      id: 'r3',
      name: 'Later',
      actions: {
        ...rule().actions,
        state: 'pending_close',
        pending_hours: null,
        owner_me: false,
        add_tags: ['later'],
        remove_tags: [],
      },
    })
    const fake = api().json('GET', `${BASE}/macros`, [note, rule({ id: 'r4', name: 'Off', active: false })])
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect(fake.calls('PUT', `${BASE}/tickets/t1/presence`)).toHaveLength(0)
    await click('[data-test=macros]')
    expect(exists('[data-test=macro-Off]')).toBe(false)
    await click('[data-test=macro-Later]')
    const body = fake.last('PATCH', `${BASE}/tickets/t1`)?.body as Record<string, unknown>
    expect(body).toMatchObject({ state: 'pending_close', tags: ['later'] })
    const hours = (new Date(String(body.pending_until)).getTime() - Date.now()) / 3_600_000
    expect(Math.round(hours)).toBe(24)
  })

  it('edits triggers that give tickets to someone', async () => {
    inTenant()
    const trigger = rule({
      id: 't9',
      kind: 'trigger',
      name: 'To Ada',
      event: 'updated',
      actions: { ...rule().actions, owner_me: false, owner_id: 'u1', state: 'pending_reminder', pending_hours: 5 },
    })
    const fake = new FakeApi()
      .json('GET', `${BASE}/triggers`, [trigger])
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member()])
      .on('PATCH', `${BASE}/triggers/t9`, (request) => ({ body: { ...trigger, ...(request.body as object) } }))
    await mountRules('trigger', 'triggers')
    await click('[data-test="edit-rule-To Ada"]')
    expect(($('#action-owner').element as HTMLSelectElement).value).toBe('u1')
    expect(($('#action-pending').element as HTMLInputElement).value).toBe('5')
    await $('#action-owner').setValue('none')
    await click('[data-test=save-rule]')
    expect(fake.last('PATCH', `${BASE}/triggers/t9`)?.body).toMatchObject({
      event: 'updated',
      actions: { unassign: true, owner_id: null, pending_hours: 5 },
    })
  })

  it('lists escalated tickets', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [])
      .json('GET', `${BASE}/tickets/counts`, { mine: 0, unassigned: 0, due: 0, open: 1, watching: 0 })
      .json('GET', `${BASE}/escalations`, [
        {
          ticket_id: 't1',
          policy_id: 'p1',
          first_response_due: null,
          solution_due: null,
          first_responded_at: null,
          solved_at: null,
          breached: [],
        },
      ])
      .json('GET', `${BASE}/tickets`, { items: [ticket()], total: 1 })
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets?view=escalated` })
    expect($('[data-test=count-escalated]').text()).toBe('1')
    expect(fake.last('GET', `${BASE}/tickets`)?.params.getAll('ids')).toEqual(['t1'])
    expect(fake.last('GET', `${BASE}/tickets`)?.query.view).toBe('open')

    fake.json('GET', `${BASE}/escalations`, [])
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets?view=escalated` })
    expect(text()).toContain('No ticket is about to miss its service level.')
  })
})
