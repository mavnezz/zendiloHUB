import { describe, expect, it } from 'vitest'
import { useSession } from '@/modules/identity/session'
import type { TenantRole } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import NewTicketView from '@/modules/tickets/views/NewTicketView.vue'
import TicketsView from '@/modules/tickets/views/TicketsView.vue'
import TicketView from '@/modules/tickets/views/TicketView.vue'
import { FakeApi } from '../../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../../support/fixtures'
import { contact, detail, message, queue, ticket } from '../../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const BASE = `/tenants/${TENANT_ID}`
const COUNTS = { mine: 1, unassigned: 2, due: 0, open: 3, watching: 0 }

function inTenant(role: TenantRole = 'owner'): void {
  useSession().start(user())
  useTenants().put(tenant({ role }))
  useTenants().select(TENANT_ID)
}

function directory(fake: FakeApi = new FakeApi()): FakeApi {
  return fake
    .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing', rights: ['view'] })])
    .json('GET', `${BASE}/members`, [member(), member({ user_id: 'u2', email: 'bob@example.org', role: 'agent' })])
}

describe('TicketsView', () => {
  it('shows the views with their counts and finds tickets', async () => {
    inTenant()
    const fake = directory()
      .json('GET', `${BASE}/tickets`, {
        items: [ticket({ tags: ['printer'], owner_id: 'u2' }), ticket({ id: 't2', number: 1002, customer: null })],
        total: 2,
      })
      .json('GET', `${BASE}/tickets/counts`, COUNTS)
    const { router } = await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets` })

    expect($('[data-test=count-unassigned]').text()).toBe('2')
    expect(exists('[data-test=count-closed]')).toBe(false)
    expect($$('[data-test=ticket-row]')).toHaveLength(2)
    expect(text()).toContain('#printer')
    expect(text()).toContain('bob@example.org')
    expect(text()).toContain('Acme')
    expect($('[data-test=count]').text()).toBe('2 tickets')
    expect(fake.last('GET', `${BASE}/tickets`)?.query).toMatchObject({ view: 'open', limit: '50' })

    await click('[data-test=view-mine]')
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBe('mine')
    expect(fake.last('GET', `${BASE}/tickets`)?.query.view).toBe('mine')

    await type('[data-test=search]', 'printer')
    $('[data-test=search]').element.closest('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('printer')
    expect(fake.last('GET', `${BASE}/tickets`)?.query.q).toBe('printer')

    await $('[aria-label=Queue]').setValue('q2')
    await flushPromises()
    expect(fake.last('GET', `${BASE}/tickets`)?.query).toMatchObject({ queue_id: 'q2', view: 'mine' })
  })

  it('changes many tickets at once', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = directory()
      .json('GET', `${BASE}/tickets`, { items: [ticket(), ticket({ id: 't2', number: 1002 })], total: 2 })
      .json('GET', `${BASE}/tickets/counts`, COUNTS)
      .json('POST', `${BASE}/tickets/bulk`, { changed: ['t1', 't2'], failed: {} })
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets` })

    expect(exists('[data-test=bulk]')).toBe(false)
    await click('[data-test=select-all] button, button[data-test=select-all]')
    expect($('[data-test=bulk]').text()).toContain('2 selected')
    await $('[data-test=bulk] select').setValue('owner:me')
    await click('[data-test=bulk-apply]')
    expect(fake.last('POST', `${BASE}/tickets/bulk`)?.body).toEqual({ ticket_ids: ['t1', 't2'], owner_id: 'u1' })
    expect(toasts.success()).toContain('2 tickets changed.')

    fake.json('POST', `${BASE}/tickets/bulk`, { changed: ['t1'], failed: { t2: 'queue_right_missing' } })
    await click('button[data-test=select-1001]')
    await click('button[data-test=select-1002]')
    await $('[data-test=bulk] select').setValue('priority:high')
    await click('[data-test=bulk-apply]')
    expect(fake.last('POST', `${BASE}/tickets/bulk`)?.body).toMatchObject({ priority: 'high' })
    expect(toasts.error()).toContain('1 changed, 1 you may not change like this.')

    for (const [action, field] of [
      ['owner:none', { owner_id: null }],
      ['state:closed', { state: 'closed' }],
      ['queue:q2', { queue_id: 'q2' }],
    ] as const) {
      await click('button[data-test=select-1001]')
      await $('[data-test=bulk] select').setValue(action)
      await click('[data-test=bulk-apply]')
      expect(fake.last('POST', `${BASE}/tickets/bulk`)?.body).toMatchObject(field)
    }
  })

  it('shows an empty view, failures and pages', async () => {
    inTenant()
    directory().json('GET', `${BASE}/tickets`, { items: [], total: 0 }).json('GET', `${BASE}/tickets/counts`, COUNTS)
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets?view=due` })
    expect(text()).toContain('No waiting ticket is due.')

    const fake = directory()
      .json('GET', `${BASE}/tickets`, { items: [ticket()], total: 120 })
      .json('GET', `${BASE}/tickets/counts`, COUNTS)
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets?view=bogus` })
    await click('[data-test=next]')
    expect(fake.last('GET', `${BASE}/tickets`)?.query).toMatchObject({ offset: '50', view: 'open' })

    directory().error('GET', `${BASE}/tickets`, 500, 'internal_error')
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets` })
    expect(exists('[data-test=error]')).toBe(true)

    const toasts = spyToasts()
    const failing = directory()
      .json('GET', `${BASE}/tickets`, { items: [ticket()], total: 1 })
      .json('GET', `${BASE}/tickets/counts`, COUNTS)
      .error('POST', `${BASE}/tickets/bulk`, 500, 'internal_error')
    await mountView(TicketsView, { path: `/t/${TENANT_ID}/tickets` })
    await click('button[data-test=select-1001]')
    await $('[data-test=bulk] select').setValue('state:open')
    await click('[data-test=bulk-apply]')
    expect(failing.calls('POST', `${BASE}/tickets/bulk`)).toHaveLength(1)
    expect(toasts.error()).toHaveLength(1)
  })
})

describe('NewTicketView', () => {
  it('opens a ticket for a found or a new customer', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = directory()
      .json('GET', `${BASE}/contacts`, { items: [contact()], total: 1 })
      .json('POST', `${BASE}/tickets`, detail({ id: 't9', number: 1009 }), 201)
    const { router } = await mountView(NewTicketView, { path: `/t/${TENANT_ID}/tickets/new` })
    // Only queues with `create` are on offer.
    expect($$('#ticket-queue option').map((option) => option.text())).toEqual(['Support'])

    const picker = $('[data-test=customer-search]')
    await picker.setValue('carl')
    await new Promise((resolve) => setTimeout(resolve, 300))
    await flushPromises()
    await click('[data-test=contact-c1]')
    expect($('[data-test=picked]').text()).toContain('Carl Customer <carl@acme.example>')
    await type('#ticket-subject', 'Printer broken')
    await type('#ticket-body', 'It does not print.')
    await type('#ticket-tags', 'printer, urgent ')
    await click('[data-test=option-note]')
    await click('[data-test=create]')
    expect(fake.last('POST', `${BASE}/tickets`)?.body).toEqual({
      queue_id: 'q1',
      subject: 'Printer broken',
      body: 'It does not print.',
      first: 'note',
      priority: 'normal',
      channel: 'web',
      tags: ['printer', 'urgent'],
      customer: { id: 'c1', name: '' },
    })
    expect(toasts.success()).toContain('Ticket #1009 created.')
    expect(router.currentRoute.value.params.ticketId).toBe('t9')
  })

  it('takes new customers by e-mail address and reports failures', async () => {
    inTenant()
    const fake = directory()
      .json('GET', `${BASE}/contacts`, { items: [], total: 0 })
      .error('POST', `${BASE}/tickets`, 403, 'queue_right_missing')
    await mountView(NewTicketView, { path: `/t/${TENANT_ID}/tickets/new` })
    await $('[data-test=customer-search]').setValue('new@customer.example')
    await click('[data-test=new-customer]')
    await click('[data-test=unpick]')
    await $('[data-test=customer-search]').setValue('+49 30 555')
    await click('[data-test=new-customer]')
    await type('#ticket-subject', 'Call')
    await type('#ticket-body', 'Called about the invoice')
    await click('[data-test=create]')
    expect(fake.last('POST', `${BASE}/tickets`)?.body).toMatchObject({
      first: 'customer',
      channel: 'phone',
      customer: { phone: '+49 30 555' },
    })
    expect($('[data-test=error]').text()).toContain('Your groups do not allow this')
  })

  it('says when no queue takes new tickets', async () => {
    inTenant('agent')
    new FakeApi().json('GET', `${BASE}/queues`, [queue({ rights: ['view'] })]).json('GET', `${BASE}/members`, [])
    await mountView(NewTicketView, { path: `/t/${TENANT_ID}/tickets/new` })
    expect(exists('[data-test=no-queue]')).toBe(true)
  })
})

describe('TicketView', () => {
  function api(shown = detail()): FakeApi {
    return directory()
      .json('GET', `${BASE}/tickets/t1`, shown)
      .json('GET', `${BASE}/tickets/t1/messages`, [
        message(),
        message({ id: 'm2', direction: 'out', author_kind: 'agent', author_name: 'ada@example.org', body: 'On it' }),
        message({ id: 'm3', kind: 'internal', direction: 'out', author_kind: 'agent', author_name: 'ada@example.org' }),
      ])
      .json('GET', `${BASE}/tickets/t1/history`, [
        {
          id: 'h1',
          actor_id: 'u1',
          actor_name: 'ada@example.org',
          action: 'changed',
          field: 'state',
          old: 'new',
          new: 'open',
          created_at: '2026-11-13T12:10:00Z',
        },
        {
          id: 'h2',
          actor_id: 'u1',
          actor_name: 'ada@example.org',
          action: 'changed',
          field: 'owner_id',
          old: null,
          new: 'u2',
          created_at: '2026-11-13T12:11:00Z',
        },
        {
          id: 'h3',
          actor_id: 'u1',
          actor_name: 'ada@example.org',
          action: 'merged_from',
          field: null,
          old: null,
          new: '1005',
          created_at: '2026-11-13T12:12:00Z',
        },
      ])
      .json('GET', `${BASE}/queues/q1/assignees`, ['u1', 'u2'])
  }

  it('shows the messages, fields and history', async () => {
    inTenant()
    api(
      detail({ time_minutes: 15, links: [{ id: 't2', number: 1002, subject: 'Other', state: 'new', kind: 'parent' }] }),
    )
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=ticket-number]').text()).toBe('#1001')
    expect($('[data-test=ticket-subject]').text()).toContain('Printer broken')
    expect($$('[data-test^=message-]').map((each) => each.attributes('data-test'))).toEqual([
      'message-public-in',
      'message-public-out',
      'message-internal-out',
    ])
    expect($('[data-test=customer-card]').text()).toContain('Acme')
    expect($('[data-test=time-total]').text()).toBe('Time spent: 15 min')
    expect($('[data-test=link-1002]').text()).toContain('the parent')
    expect($$('#field-owner option').map((option) => option.text())).toEqual(['Nobody', 'Me', 'bob@example.org'])

    await $('[data-test=tab-history]').trigger('mousedown', { button: 0 })
    await flushPromises()
    expect($$('[data-test=history-entry]').map((entry) => entry.text())).toEqual([
      expect.stringContaining('changed the state from New to Open'),
      expect.stringContaining('changed the owner from – to bob@example.org'),
      expect.stringContaining('merged #1005 into this ticket'),
    ])
  })

  it('writes replies and notes with mentions, state and time', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api().json('POST', `${BASE}/tickets/t1/messages`, message(), 201)
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })

    await type('[data-test=composer-body]', 'Have you tried turning it off?')
    await $('#composer-state').setValue('pending_reminder')
    await type('#composer-pending', '2026-11-20T09:00')
    await type('#composer-minutes', '5')
    await click('[data-test=send]')
    expect(fake.last('POST', `${BASE}/tickets/t1/messages`)?.body).toEqual({
      kind: 'public',
      direction: 'out',
      body: 'Have you tried turning it off?',
      mentions: [],
      state: 'pending_reminder',
      pending_until: new Date('2026-11-20T09:00').toISOString(),
      time_minutes: 5,
    })
    expect(toasts.success()).toContain('Reply saved.')

    await click('[data-test=option-note]')
    await type('[data-test=composer-body]', '@bob please check, cc @nobody')
    await click('[data-test=send]')
    expect(fake.last('POST', `${BASE}/tickets/t1/messages`)?.body).toMatchObject({ kind: 'internal', mentions: ['u2'] })

    await click('[data-test=option-customer]')
    await type('[data-test=composer-body]', 'Called again')
    await click('[data-test=send]')
    expect(fake.last('POST', `${BASE}/tickets/t1/messages`)?.body).toMatchObject({ kind: 'public', direction: 'in' })

    fake.error('POST', `${BASE}/tickets/t1/messages`, 403, 'queue_right_missing')
    await type('[data-test=composer-body]', 'x')
    await click('[data-test=send]')
    expect(toasts.error()).toHaveLength(1)
  })

  it('changes the fields', async () => {
    inTenant()
    const fake = api().on('PATCH', `${BASE}/tickets/t1`, (request) => ({
      body: { ...detail(), ...(request.body as object) },
    }))
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })

    await $('#field-priority').setValue('urgent')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ priority: 'urgent' })
    await $('#field-owner').setValue('u2')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ owner_id: 'u2' })
    await $('#field-responsible').setValue('u1')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ responsible_id: 'u1' })
    await $('#field-queue').setValue('q1')
    await $('#field-state').setValue('closed')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ state: 'closed' })
    await $('#field-state').setValue('pending_close')
    await flushPromises()
    await $('#field-pending').setValue('2026-11-20T09:00')
    await $('#field-pending').trigger('change')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({
      state: 'pending_close',
      pending_until: new Date('2026-11-20T09:00').toISOString(),
    })
    await type('#field-tags', 'printer, toner')
    await $('#field-tags').trigger('blur')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ tags: ['printer', 'toner'] })

    await click('[data-test=edit-subject]')
    await type('#ticket-subject', 'Printer jammed')
    await click('[data-test=save-subject]')
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ subject: 'Printer jammed' })

    fake.error('PATCH', `${BASE}/tickets/t1`, 422, 'not_assignable')
    const toasts = spyToasts()
    await $('#field-owner').setValue('u1')
    await flushPromises()
    expect(toasts.error()).toContain('This person may not reply in the queue of the ticket.')
  })

  it('changes the customer, watches, links, merges, splits and deletes', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api()
      .json('GET', `${BASE}/contacts`, { items: [], total: 0 })
      .json('POST', `${BASE}/contacts`, contact({ id: 'c9' }), 201)
      .json('PATCH', `${BASE}/tickets/t1`, detail())
      .on('PUT', `${BASE}/tickets/t1/watch`, { status: 204 })
      .json(
        'POST',
        `${BASE}/tickets/t1/links`,
        detail({ links: [{ id: 't2', number: 1002, subject: 'X', state: 'new', kind: 'related' }] }),
      )
      .on('DELETE', `${BASE}/tickets/t1/links/t2`, { status: 204 })
      .json('POST', `${BASE}/tickets/t1/merge`, detail({ id: 't2', number: 1002 }))
      .json('POST', `${BASE}/tickets/t1/split`, detail({ id: 't3', number: 1003 }), 201)
      .on('DELETE', `${BASE}/tickets/t1`, { status: 204 })
    const { router } = await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })

    await click('[data-test=change-customer]')
    await $('[data-test=customer-search]').setValue('dora@else.example')
    await click('[data-test=new-customer]')
    await flushPromises()
    expect(fake.last('POST', `${BASE}/contacts`)?.body).toMatchObject({ email: 'dora@else.example' })
    expect(fake.last('PATCH', `${BASE}/tickets/t1`)?.body).toEqual({ customer_id: 'c9' })

    await click('[data-test=watch]')
    expect(fake.calls('PUT', `${BASE}/tickets/t1/watch`)).toHaveLength(1)
    expect(toasts.success()).toContain('You watch this ticket now.')

    await click('[data-test=link]')
    await type('#other-number', '#1002')
    await $('#link-kind').setValue('related')
    await click('[data-test=confirm-number]')
    expect(fake.last('POST', `${BASE}/tickets/t1/links`)?.body).toEqual({ number: 1002, kind: 'related' })
    await click('[data-test=unlink-1002]')
    expect(fake.calls('DELETE', `${BASE}/tickets/t1/links/t2`)).toHaveLength(1)

    await click('[data-test=split-m1]')
    expect(fake.last('POST', `${BASE}/tickets/t1/split`)?.body).toEqual({ message_id: 'm1' })
    expect(router.currentRoute.value.params.ticketId).toBe('t3')
    await router.push(`/t/${TENANT_ID}/tickets/t1`)
    await flushPromises()

    await click('[data-test=merge]')
    await type('#other-number', '1002')
    await click('[data-test=confirm-number]')
    expect(fake.last('POST', `${BASE}/tickets/t1/merge`)?.body).toEqual({ number: 1002 })
    expect(router.currentRoute.value.params.ticketId).toBe('t2')
    await router.push(`/t/${TENANT_ID}/tickets/t1`)
    await flushPromises()

    await click('[data-test=delete]')
    expect(text()).toContain('Delete ticket #1001?')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/tickets/t1`)).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('tickets')
  })

  it('starts replies with the queue draft, shows deliveries and formatted e-mails', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api()
      .json('GET', `${BASE}/tickets/t1/messages`, [
        message({ from_address: 'carl@acme.example', body_html: '<p>It does <b>not</b> print.</p>' }),
        message({ id: 'm2', direction: 'out', author_kind: 'agent', author_name: 'ada@example.org', body: 'On it' }),
        message({ id: 'm3', direction: 'out', author_kind: 'agent', author_name: 'ada@example.org', body: 'Again' }),
        message({ id: 'm4', direction: 'out', author_kind: 'agent', author_name: 'ada@example.org', body: 'Phone' }),
      ])
      .json('GET', `${BASE}/tickets/t1/deliveries`, [
        { message_id: 'm2', status: 'sent', error: null, attempts: 1, updated_at: '2026-11-13T12:00:00Z' },
        { message_id: 'm3', status: 'failed', error: 'No answer', attempts: 5, updated_at: '2026-11-13T12:00:00Z' },
        {
          message_id: 'm4',
          status: 'skipped',
          error: 'no_customer_address',
          attempts: 0,
          updated_at: '2026-11-13T12:00:00Z',
        },
      ])
      .json('GET', `${BASE}/queues/q1/reply-draft`, { text: 'Hello Carl,\n\n\n\nBest regards' })
      .on('POST', `${BASE}/tickets/t1/deliveries/m3/resend`, { status: 202 })
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect(fake.last('GET', `${BASE}/queues/q1/reply-draft`)?.query).toMatchObject({
      number: '1001',
      customer_name: 'Carl Customer',
    })
    const body = () => ($('[data-test=composer-body]').element as HTMLTextAreaElement).value
    expect(body()).toBe('Hello Carl,\n\n\n\nBest regards')
    expect($('[data-test=send]').attributes('disabled')).toBeDefined()
    await click('[data-test=option-note]')
    expect(body()).toBe('')
    await click('[data-test=option-reply]')
    expect(body()).toBe('Hello Carl,\n\n\n\nBest regards')

    expect($('[data-test=delivery-m2]').text()).toContain('sent by e-mail')
    expect($('[data-test=delivery-m4]').text()).toContain('the customer has no e-mail address')
    expect($('[data-test=delivery-m3]').attributes('title')).toBe('No answer')
    await click('[data-test=resend-m3]')
    expect(fake.calls('POST', `${BASE}/tickets/t1/deliveries/m3/resend`)).toHaveLength(1)
    expect(toasts.success()).toContain('Sending again.')

    expect(text()).toContain('carl@acme.example')
    await click('[data-test=formatted-m1]')
    expect($('[data-test=message-public-in] b').text()).toBe('not')
    await click('[data-test=formatted-m1]')
    expect(exists('[data-test=message-public-in] b')).toBe(false)

    fake.error('POST', `${BASE}/tickets/t1/deliveries/m3/resend`, 500, 'internal_error')
    await click('[data-test=resend-m3]')
    expect(toasts.error()).toHaveLength(1)
  })

  it('shows merged tickets and readers without controls, and failures', async () => {
    inTenant('agent')
    api(
      detail({
        state: 'merged',
        merged_into: { id: 't2', number: 1002 },
        rights: ['view'],
        customer: null,
        watching: true,
      }),
    )
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=merged-into]').text()).toContain('#1002')
    expect(exists('[data-test=composer]')).toBe(false)
    expect(exists('[data-test=merge]')).toBe(false)
    expect(exists('[data-test=delete]')).toBe(false)
    expect($('[data-test=watch]').text()).toContain('Stop watching')
    expect(text()).toContain('No customer')

    directory().error('GET', `${BASE}/tickets/t1`, 404, 'ticket_not_found')
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=error]').text()).toContain('does not exist')
  })
})
