import { describe, expect, it } from 'vitest'
import PortalHomeView from '@/modules/portal/views/PortalHomeView.vue'
import PortalSettingsView from '@/modules/portal/views/PortalSettingsView.vue'
import PortalTicketView from '@/modules/portal/views/PortalTicketView.vue'
import PortalVerifyView from '@/modules/portal/views/PortalVerifyView.vue'
import { useSession } from '@/modules/identity/session'
import { useTenants } from '@/modules/tenancy/tenants'
import TicketView from '@/modules/tickets/views/TicketView.vue'
import { FakeApi } from '../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../support/fixtures'
import { detail, message, queue, ticket } from '../support/helpdesk'
import { $, $$, click, exists, mountView, text, type } from '../support/mount'
import { spyToasts } from '../support/toasts'

const BASE = `/tenants/${TENANT_ID}`
const PORTAL = `/portal/${TENANT_ID}`

const VISITOR = { name: 'Carl', email: 'carl@acme.example', company_name: 'Acme', company_tickets: false }
const PORTAL_TICKET = {
  id: 't1',
  number: 1001,
  subject: 'Printer broken',
  state: 'waiting' as const,
  created_at: '2026-11-13T12:00:00Z',
  updated_at: '2026-11-14T09:00:00Z',
}
const THREAD = {
  ticket: PORTAL_TICKET,
  messages: [
    {
      id: 'm1',
      from_customer: true,
      author_name: 'Carl',
      body: 'It does not print.',
      created_at: '2026-11-13T12:00:00Z',
    },
    {
      id: 'm2',
      from_customer: false,
      author_name: 'Ada',
      body: 'Please restart it.',
      created_at: '2026-11-13T13:00:00Z',
    },
  ],
}

function inTenant(): void {
  useSession().start(user())
  useTenants().put(tenant({ role: 'owner' }))
  useTenants().select(TENANT_ID)
}

function ticketMocks(fake: FakeApi): FakeApi {
  return fake
    .json('GET', `${BASE}/queues`, [queue()])
    .json('GET', `${BASE}/members`, [member()])
    .json('GET', `${BASE}/tickets/t1`, detail())
    .json('GET', `${BASE}/tickets/t1/messages`, [message()])
    .json('GET', `${BASE}/tickets/t1/history`, [])
}

describe('PortalHomeView', () => {
  it('signs in with a link by e-mail', async () => {
    const fake = new FakeApi()
      .error('GET', `${PORTAL}/me`, 401, 'portal_login_required')
      .on('POST', `${PORTAL}/login`, {
        status: 202,
      })
    await mountView(PortalHomeView, { path: `/portal/${TENANT_ID}` })
    expect(text()).toContain('Sign in')
    await type('[data-test=portal-email]', ' carl@acme.example ')
    await click('[data-test=portal-send-link]')
    expect(fake.last('POST', `${PORTAL}/login`)!.body).toEqual({ email: 'carl@acme.example' })
    expect($('[data-test=portal-sent]').text()).toContain('a link is on its way')
  })

  it('says so when the portal is closed', async () => {
    new FakeApi().error('GET', `${PORTAL}/me`, 403, 'portal_closed')
    await mountView(PortalHomeView, { path: `/portal/${TENANT_ID}` })
    expect(exists('[data-test=portal-closed]')).toBe(true)
  })

  it('reports a closed portal when asking for a link, and other errors', async () => {
    const fake = new FakeApi()
      .error('GET', `${PORTAL}/me`, 500, 'boom', 'Server down')
      .error('POST', `${PORTAL}/login`, 422, 'invalid_portal')
    await mountView(PortalHomeView, { path: `/portal/${TENANT_ID}` })
    expect(text()).toContain('Server down')
    await type('[data-test=portal-email]', 'carl@acme.example')
    await click('[data-test=portal-send-link]')
    expect(text()).toContain('Please check your request')
    fake.error('POST', `${PORTAL}/login`, 403, 'portal_closed')
    await click('[data-test=portal-send-link]')
    expect(exists('[data-test=portal-closed]')).toBe(true)
  })

  it('lists the tickets, opens new ones and signs out', async () => {
    const fake = new FakeApi()
      .json('GET', `${PORTAL}/me`, VISITOR)
      .json('GET', `${PORTAL}/tickets`, [PORTAL_TICKET, { ...PORTAL_TICKET, id: 't2', state: 'closed' }])
      .json('POST', `${PORTAL}/tickets`, { ...PORTAL_TICKET, id: 't3' }, 201)
      .on('POST', `${PORTAL}/logout`, { status: 204 })
    const { router } = await mountView(PortalHomeView, { path: `/portal/${TENANT_ID}` })
    expect($('[data-test=visitor]').text()).toContain('Carl · Acme')
    expect($$('[data-test^=portal-ticket-]')).toHaveLength(2)
    expect($('[data-test=portal-ticket-t1]').text()).toContain('Waiting for you')
    expect($('[data-test=portal-ticket-t2]').text()).toContain('Closed')

    await click('[data-test=portal-new]')
    await type('[data-test=portal-subject]', 'Toner')
    await type('[data-test=portal-body]', 'Need toner')
    await click('[data-test=portal-submit]')
    expect(fake.last('POST', `${PORTAL}/tickets`)!.body).toEqual({ subject: 'Toner', body: 'Need toner' })
    expect(router.currentRoute.value.name).toBe('portalTicket')
    expect(router.currentRoute.value.params.ticketId).toBe('t3')
  })

  it('shows the company view, an empty list, failures and signs out', async () => {
    const fake = new FakeApi()
      .json('GET', `${PORTAL}/me`, { ...VISITOR, company_name: null, company_tickets: true })
      .json('GET', `${PORTAL}/tickets`, [])
      .error('POST', `${PORTAL}/tickets`, 422, 'invalid_portal')
      .on('POST', `${PORTAL}/logout`, { status: 204 })
    await mountView(PortalHomeView, { path: `/portal/${TENANT_ID}` })
    expect(text()).toContain('Tickets of your company')
    expect(exists('[data-test=portal-empty]')).toBe(true)
    await click('[data-test=portal-new]')
    await type('[data-test=portal-subject]', 'X')
    await type('[data-test=portal-body]', 'Y')
    await click('[data-test=portal-submit]')
    expect(text()).toContain('Please check your request')
    await click('[data-test=portal-logout]')
    expect(fake.calls('POST', `${PORTAL}/logout`)).toHaveLength(1)
    expect(text()).toContain('Sign in')
  })
})

describe('PortalVerifyView', () => {
  it('signs in with the token and leads to the tickets', async () => {
    const fake = new FakeApi().json('POST', `${PORTAL}/verify`, VISITOR)
    const { router } = await mountView(PortalVerifyView, { path: `/portal/${TENANT_ID}/verify?token=abc` })
    expect(fake.last('POST', `${PORTAL}/verify`)!.body).toEqual({ token: 'abc' })
    expect(router.currentRoute.value.name).toBe('portal')
  })

  it('explains an expired link', async () => {
    new FakeApi().error('POST', `${PORTAL}/verify`, 400, 'portal_link_invalid')
    await mountView(PortalVerifyView, { path: `/portal/${TENANT_ID}/verify` })
    expect(text()).toContain('This link is invalid or has expired')
    expect(exists('[data-test=portal-again]')).toBe(true)
  })
})

describe('PortalTicketView', () => {
  it('shows the conversation and sends a reply', async () => {
    const fake = new FakeApi()
      .json('GET', `${PORTAL}/tickets/t1`, THREAD)
      .json('POST', `${PORTAL}/tickets/t1/messages`, {
        ticket: { ...PORTAL_TICKET, state: 'closed' },
        messages: [...THREAD.messages, { ...THREAD.messages[0]!, id: 'm3', body: 'Still broken' }],
      })
    await mountView(PortalTicketView, { path: `/portal/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=portal-subject-title]').text()).toContain('#1001')
    expect($('[data-test=portal-message-m1]').text()).toContain('You')
    expect($('[data-test=portal-message-m2]').text()).toContain('Ada')
    await type('[data-test=portal-reply]', 'Still broken')
    await click('[data-test=portal-answer]')
    expect(fake.last('POST', `${PORTAL}/tickets/t1/messages`)!.body).toEqual({ body: 'Still broken' })
    expect(exists('[data-test=portal-message-m3]')).toBe(true)
    expect(text()).toContain('Replying opens the ticket again.')

    fake.error('POST', `${PORTAL}/tickets/t1/messages`, 404, 'ticket_not_found')
    await type('[data-test=portal-reply]', 'Again')
    await click('[data-test=portal-answer]')
    expect(text()).toContain('The ticket does not exist')
  })

  it('reports a ticket it may not show', async () => {
    new FakeApi().error('GET', `${PORTAL}/tickets/t9`, 404, 'ticket_not_found')
    await mountView(PortalTicketView, { path: `/portal/${TENANT_ID}/tickets/t9` })
    expect(text()).toContain('The ticket does not exist')
  })
})

describe('PortalSettingsView', () => {
  it('switches the portal on for a queue', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = new FakeApi()
      .json('GET', `${BASE}/portal-settings`, { enabled: false, queue_id: null, company_tickets: false })
      .json('GET', `${BASE}/queues`, [queue()])
      .json('PUT', `${BASE}/portal-settings`, { enabled: true, queue_id: 'q1', company_tickets: true })
    await mountView(PortalSettingsView, { path: `/t/${TENANT_ID}/customerPortal` })
    expect(($('[data-test=portal-address]').element as HTMLInputElement).value).toContain(`/portal/${TENANT_ID}`)
    await click('[data-test=portal-enabled]')
    await click('[data-test=portal-company]')
    await $('[data-test=portal-queue] select').setValue('q1')
    await click('[data-test=portal-save]')
    expect(fake.last('PUT', `${BASE}/portal-settings`)!.body).toEqual({
      enabled: true,
      queue_id: 'q1',
      company_tickets: true,
    })
    expect(toasts.success()).toContain('The portal settings were saved.')

    fake.error('PUT', `${BASE}/portal-settings`, 422, 'invalid_portal')
    await click('[data-test=portal-save]')
    expect(text()).toContain('Please check your request')
  })

  it('shows a failure to load', async () => {
    inTenant()
    new FakeApi()
      .error('GET', `${BASE}/portal-settings`, 403, 'forbidden', 'Not allowed')
      .json('GET', `${BASE}/queues`, [])
    await mountView(PortalSettingsView, { path: `/t/${TENANT_ID}/customerPortal` })
    expect(text()).toContain('You are not allowed to do this.')
  })
})

describe('TicketView with the AI assistant and similar tickets', () => {
  it('summarizes, drafts a reply and links similar tickets', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = ticketMocks(new FakeApi())
      .json('GET', `${BASE}/assistant`, { enabled: true })
      .json('GET', `${BASE}/tickets/t1/similar`, {
        items: [ticket({ id: 't2', number: 1002, subject: 'Printer jam' })],
        total: 1,
      })
      .json('POST', `${BASE}/tickets/t1/assist`, { text: 'Carl cannot print.' })
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=similar-t2]').text()).toContain('#1002')

    await click('[data-test=summarize]')
    expect(fake.last('POST', `${BASE}/tickets/t1/assist`)!.body).toEqual({ task: 'summary' })
    expect($('[data-test=assist-summary]').text()).toBe('Carl cannot print.')
    expect($('[data-test=summarize]').text()).toContain('Summarize again')

    fake.json('POST', `${BASE}/tickets/t1/assist`, { text: 'Dear Carl, please restart it.' })
    await click('[data-test=draft-ai]')
    expect(fake.last('POST', `${BASE}/tickets/t1/assist`)!.body).toEqual({ task: 'reply' })
    const body = () => ($('[data-test=composer-body]').element as HTMLTextAreaElement).value
    expect(body()).toBe('Dear Carl, please restart it.')
    await type('[data-test=composer-body]', 'Hello')
    await click('[data-test=draft-ai]')
    expect(body()).toBe('Hello\n\nDear Carl, please restart it.')

    fake.on('POST', `${BASE}/tickets/t1/assist`, {
      status: 502,
      body: { error: 'assistant_failed', message: 'x', params: { reason: 'refused' } },
    })
    await click('[data-test=draft-ai]')
    expect(toasts.error()).toContain('The AI assistant could not answer (refused).')
    await click('[data-test=summarize]')
    expect($('[data-test=assist-error]').text()).toContain('The AI assistant could not answer')
  })

  it('hides the assistant without a key', async () => {
    inTenant()
    ticketMocks(new FakeApi())
      .json('GET', `${BASE}/assistant`, { enabled: false })
      .json('GET', `${BASE}/tickets/t1/similar`, { items: [], total: 0 })
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    expect(exists('[data-test=assist]')).toBe(false)
    expect(exists('[data-test=draft-ai]')).toBe(false)
    expect(exists('[data-test=similar]')).toBe(false)
  })
})
