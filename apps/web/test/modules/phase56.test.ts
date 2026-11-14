import { describe, expect, it } from 'vitest'
import WebhooksView from '@/modules/integrations/views/WebhooksView.vue'
import type { Article } from '@/modules/knowledge/api'
import ArticlesView from '@/modules/knowledge/views/ArticlesView.vue'
import HelpCenterView from '@/modules/knowledge/views/HelpCenterView.vue'
import AssistantsView from '@/modules/mcp/views/AssistantsView.vue'
import ReportsView from '@/modules/reporting/views/ReportsView.vue'
import { useSession } from '@/modules/identity/session'
import type { TenantRole } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import TicketView from '@/modules/tickets/views/TicketView.vue'
import { FakeApi } from '../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../support/fixtures'
import { detail, message, queue } from '../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../support/mount'
import { spyToasts } from '../support/toasts'

const BASE = `/tenants/${TENANT_ID}`

function inTenant(role: TenantRole = 'owner'): void {
  useSession().start(user())
  useTenants().put(tenant({ role }))
  useTenants().select(TENANT_ID)
}

function article(overrides: Partial<Article> = {}): Article {
  return {
    id: 'a1',
    title: 'Reset your password',
    body: 'Click "Forgot password".',
    category: 'Account',
    tags: ['login'],
    visibility: 'public',
    author: 'ada@example.org',
    created_at: '2026-11-13T12:00:00Z',
    updated_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

const REPORT = {
  created: 12,
  closed: 9,
  open_now: 5,
  unassigned_now: 2,
  first_response_median: 42,
  first_response_average: 50,
  resolution_median: 1560,
  breached: 1,
  reopened: 3,
  days: [
    { day: '2026-11-12', created: 4, closed: 2 },
    { day: '2026-11-13', created: 8, closed: 7 },
  ],
  queues: [{ key: 'q1', created: 12, closed: 9, open: 5 }],
  owners: [
    { key: 'u1', created: 5, closed: 4, open: 1 },
    { key: null, created: 7, closed: 5, open: 4 },
  ],
  channels: [{ key: 'email', created: 12, closed: 9, open: 5 }],
}

describe('ReportsView', () => {
  it('shows the figures, the chart with a tooltip and the table', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member()])
      .json('GET', `${BASE}/reports`, REPORT)
    await mountView(ReportsView, { path: `/t/${TENANT_ID}/reports` })
    expect($('[data-test=tile-created]').text()).toContain('12')
    expect($('[data-test=tile-firstResponse]').text()).toContain('42 min')
    expect($('[data-test=tile-resolution]').text()).toContain('1.1 days')
    expect($('[data-test=tile-openNow]').text()).toContain('2 unassigned')
    expect($('[data-test=legend]').text()).toContain('Opened')
    expect($('[data-test=groups-owners]').text()).toContain('ada@example.org')
    expect($('[data-test=groups-owners]').text()).toContain('Nobody')
    expect($('[data-test=groups-channels]').text()).toContain('E-mail')
    expect($('[data-test=groups-queues]').text()).toContain('Support')

    await $('[data-test="day-2026-11-13"]').trigger('mouseenter')
    expect($('[data-test=chart-tooltip]').text()).toContain('Opened: 8')
    await $('[data-test="day-2026-11-13"]').trigger('mouseleave')
    expect(exists('[data-test=chart-tooltip]')).toBe(false)

    await click('[data-test=toggle-table]')
    expect($$('[data-test=day-table] tbody tr')).toHaveLength(2)

    await click('[data-test=option-7]')
    await flushPromises()
    const query = fake.last('GET', `${BASE}/reports`)?.query
    expect(query?.timezone).toBeTruthy()
    const span = (new Date(query!.end!).getTime() - new Date(query!.start!).getTime()) / 86_400_000
    expect(span).toBe(6)
    await $('[aria-label=Queue]').setValue('q1')
    await flushPromises()
    expect(fake.last('GET', `${BASE}/reports`)?.query.queue_id).toBe('q1')
  })

  it('shows short times and failures', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/queues`, [])
      .json('GET', `${BASE}/members`, [])
      .json('GET', `${BASE}/reports`, {
        ...REPORT,
        first_response_median: null,
        resolution_median: 90,
        queues: [],
        days: [],
      })
    await mountView(ReportsView, { path: `/t/${TENANT_ID}/reports` })
    expect($('[data-test=tile-firstResponse]').text()).toContain('–')
    expect($('[data-test=tile-resolution]').text()).toContain('1.5 h')
    expect($('[data-test=groups-queues]').text()).toContain('Nothing in this period.')

    new FakeApi().json('GET', `${BASE}/queues`, []).error('GET', `${BASE}/reports`, 403, 'permission_denied')
    await mountView(ReportsView, { path: `/t/${TENANT_ID}/reports` })
    expect(text()).toContain('Your role does not allow this.')
  })
})

describe('WebhooksView', () => {
  const hook = {
    id: 'w1',
    name: 'CRM',
    url: 'https://crm.example/hook',
    events: ['ticket.created'],
    active: true,
    format: 'json',
    queue_ids: [],
    created_at: '2026-11-13T12:00:00Z',
    last_delivery_at: null,
    last_status: null,
    last_error: 'HTTP 500',
    secret: null,
  }

  it('creates webhooks, shows the secret once, tests and lists deliveries', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/webhooks`, [hook, { ...hook, id: 'w2', name: 'Off', active: false, last_error: null }])
      .on('POST', `${BASE}/webhooks`, (request) => ({
        status: 201,
        body: { ...hook, id: 'w3', ...(request.body as object), secret: 'whsec_abc' },
      }))
      .on('PATCH', `${BASE}/webhooks/w1`, (request) => ({ body: { ...hook, ...(request.body as object) } }))
      .on('POST', `${BASE}/webhooks/w1/test`, { status: 202 })
      .json('GET', `${BASE}/webhooks/w1/deliveries`, [
        {
          id: 'd1',
          event: 'ticket.created',
          attempt: 2,
          status: 500,
          error: 'HTTP 500',
          created_at: '2026-11-13T12:00:00Z',
        },
        { id: 'd2', event: 'ticket.created', attempt: 1, status: 204, error: null, created_at: '2026-11-13T11:00:00Z' },
      ])
      .on('DELETE', `${BASE}/webhooks/w1`, { status: 204 })
    await mountView(WebhooksView, { path: `/t/${TENANT_ID}/webhooks` })
    expect($('[data-test=webhook-CRM]').text()).toContain('HTTP 500')
    expect($('[data-test=webhook-Off]').text()).toContain('off')

    await click('[data-test=create-webhook]')
    await type('#webhook-name', 'Chat')
    await type('#webhook-url', 'https://chat.example/in')
    await click('[data-test="event-message.added"] button')
    await click('[data-test=save-webhook]')
    expect(fake.last('POST', `${BASE}/webhooks`)?.body).toEqual({
      name: 'Chat',
      url: 'https://chat.example/in',
      events: ['ticket.created', 'message.added'],
      active: true,
      new_secret: false,
      format: 'json',
      queue_ids: [],
    })
    expect($('[data-test=secret]').text()).toContain('whsec_abc')
    await click('[data-test=copy-secret]')

    await click('[data-test=edit-CRM]')
    await click('[data-test="event-ticket.created"] button')
    await click('[data-test="event-sla.breached"] button')
    await click('[data-test=new-secret]')
    await click('[data-test=save-webhook]')
    expect(fake.last('PATCH', `${BASE}/webhooks/w1`)?.body).toMatchObject({
      events: ['sla.breached'],
      new_secret: true,
    })

    await click('[data-test=test-CRM]')
    expect(toasts.success()).toContain('A test event is on its way.')
    await click('[data-test=deliveries-CRM]')
    expect($('[data-test=delivery-list]').text()).toContain('try 2')
    expect($('[data-test=delivery-list]').text()).toContain('204')

    await click('[data-test=delete-CRM]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/webhooks/w1`)).toHaveLength(1)

    fake.error('POST', `${BASE}/webhooks/w1/test`, 404, 'webhook_not_found')
    await click('[data-test=test-CRM]')
    expect(toasts.error()).toContain('The webhook does not exist.')
    fake.error('POST', `${BASE}/webhooks`, 422, 'invalid_webhook')
    await click('[data-test=create-webhook]')
    await type('#webhook-name', 'X')
    await type('#webhook-url', 'https://x.example')
    await click('[data-test=save-webhook]')
    expect(text()).toContain('Please check the webhook')
  })

  it('shows an empty list and failures', async () => {
    inTenant()
    new FakeApi().json('GET', `${BASE}/webhooks`, [])
    await mountView(WebhooksView, { path: `/t/${TENANT_ID}/webhooks` })
    expect(text()).toContain('No webhooks yet')
    new FakeApi().error('GET', `${BASE}/webhooks`, 500, 'internal_error')
    await mountView(WebhooksView, { path: `/t/${TENANT_ID}/webhooks` })
    expect(exists('[data-test=error]')).toBe(true)
  })
})

describe('ArticlesView and HelpCenterView', () => {
  it('reads, searches, writes and deletes articles', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/articles`, {
        articles: [article(), article({ id: 'a2', title: 'Refunds', visibility: 'internal', category: '', tags: [] })],
        categories: ['Account'],
      })
      .on('POST', `${BASE}/articles`, (request) => ({
        status: 201,
        body: article({ id: 'a3', ...(request.body as object) }),
      }))
      .on('PATCH', `${BASE}/articles/a1`, (request) => ({ body: article({ ...(request.body as object) }) }))
      .on('DELETE', `${BASE}/articles/a1`, { status: 204 })
    await mountView(ArticlesView, { path: `/t/${TENANT_ID}/knowledge-base` })
    expect(text()).toContain('Pick an article.')
    await click('[data-test=article-a1]')
    expect($('[data-test=reading]').text()).toContain('Everyone (help center)')
    expect($('[data-test=reading]').text()).toContain('#login')

    await type('[data-test=search]', 'password')
    $('[data-test=search]').element.closest('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()
    expect(fake.last('GET', `${BASE}/articles`)?.query.q).toBe('password')
    await $('[aria-label=Category]').setValue('Account')
    await flushPromises()
    expect(fake.last('GET', `${BASE}/articles`)?.query.category).toBe('Account')

    await click('[data-test=create-article]')
    await type('#article-title', 'Shipping')
    await type('#article-body', 'Within 3 days.')
    await type('#article-tags', 'delivery, shop')
    await $('#article-visibility').setValue('public')
    await click('[data-test=save-article]')
    expect(fake.last('POST', `${BASE}/articles`)?.body).toEqual({
      title: 'Shipping',
      body: 'Within 3 days.',
      category: '',
      tags: ['delivery', 'shop'],
      visibility: 'public',
    })
    expect(toasts.success()).toContain('"Shipping" saved.')

    expect($('[data-test=reading]').text()).toContain('Shipping')
    await click('[data-test=article-a1]')
    await click('[data-test=edit-article]')
    await type('#article-title', 'Reset it')
    await click('[data-test=save-article]')
    expect(fake.last('PATCH', `${BASE}/articles/a1`)?.body).toMatchObject({ title: 'Reset it' })
    await click('[data-test=delete-article]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/articles/a1`)).toHaveLength(1)

    fake.error('POST', `${BASE}/articles`, 422, 'invalid_article')
    await click('[data-test=create-article]')
    await type('#article-title', 'X')
    await type('#article-body', 'Y')
    await click('[data-test=save-article]')
    expect(text()).toContain('Please check the article')
  })

  it('shows agents the articles without controls, and an empty list', async () => {
    inTenant('agent')
    new FakeApi().json('GET', `${BASE}/articles`, { articles: [], categories: [] })
    await mountView(ArticlesView, { path: `/t/${TENANT_ID}/knowledge-base` })
    expect(text()).toContain('No articles yet')
    expect(exists('[data-test=create-article]')).toBe(false)
  })

  it('serves the help center to anyone', async () => {
    const fake = new FakeApi()
      .json('GET', `/help/${TENANT_ID}`, { articles: [article()], categories: ['Account'] })
      .json('GET', `/help/${TENANT_ID}/a1`, article())
    const { router } = await mountView(HelpCenterView, { path: `/help/${TENANT_ID}` })
    expect(text()).toContain('Reset your password')
    await type('[data-test=help-search]', 'password')
    $('[data-test=help-search]').element.closest('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()
    expect(fake.last('GET', `/help/${TENANT_ID}`)?.query.q).toBe('password')
    await router.push(`/help/${TENANT_ID}/a1`)
    await flushPromises()
    await mountView(HelpCenterView, { path: `/help/${TENANT_ID}/a1` })
    expect($('[data-test=help-article]').text()).toContain('Forgot password')

    new FakeApi().json('GET', `/help/${TENANT_ID}`, { articles: [], categories: [] })
    await mountView(HelpCenterView, { path: `/help/${TENANT_ID}` })
    expect(text()).toContain('No articles yet.')
  })
})

describe('AssistantsView', () => {
  it('connects an assistant, shows the token once and disconnects it', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/mcp-connections`, [
        {
          id: 'c1',
          name: 'Claude Desktop',
          start: 'zhm_abcdefg',
          created_at: '2026-11-13T12:00:00Z',
          last_used_at: '2026-11-13T13:00:00Z',
          token: null,
        },
        {
          id: 'c2',
          name: 'Cursor',
          start: 'zhm_hijklmn',
          created_at: '2026-11-13T12:00:00Z',
          last_used_at: null,
          token: null,
        },
      ])
      .json(
        'POST',
        `${BASE}/mcp-connections`,
        {
          id: 'c3',
          name: 'Claude',
          start: 'zhm_secret0',
          created_at: '2026-11-13T12:00:00Z',
          last_used_at: null,
          token: 'zhm_secret',
        },
        201,
      )
      .on('DELETE', `${BASE}/mcp-connections/c1`, { status: 204 })
    await mountView(AssistantsView, { path: `/t/${TENANT_ID}/ai-assistants` })
    expect($('[data-test="connection-Claude Desktop"]').text()).toContain('last used')
    expect($('[data-test=connection-Cursor]').text()).toContain('not used yet')

    await click('[data-test=connect]')
    expect(fake.last('POST', `${BASE}/mcp-connections`)?.body).toEqual({ name: 'Claude' })
    expect($('[data-test=token]').text()).toContain('claude mcp add --transport http zendilohub')
    expect($('[data-test=token]').text()).toContain('Bearer zhm_secret')
    await click('[data-test=copy-json]')
    expect(toasts.success()).toContain('Copied.')

    await click('[data-test="disconnect-Claude Desktop"]')
    expect(fake.calls('DELETE', `${BASE}/mcp-connections/c1`)).toHaveLength(1)
    expect(toasts.success()).toContain('Disconnected: the token no longer works.')

    fake.error('POST', `${BASE}/mcp-connections`, 422, 'invalid_connection')
    await click('[data-test=connect]')
    expect(text()).toContain('Please check the connection')
    fake.error('DELETE', `${BASE}/mcp-connections/c2`, 404, 'connection_not_found')
    await click('[data-test=disconnect-Cursor]')
    expect(toasts.error()).toContain('The connection does not exist.')
  })
})

describe('Composer with articles', () => {
  it('inserts an article of the knowledge base', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member()])
      .json('GET', `${BASE}/tickets/t1`, detail())
      .json('GET', `${BASE}/tickets/t1/messages`, [message()])
      .json('GET', `${BASE}/tickets/t1/history`, [])
      .json('GET', `${BASE}/articles`, { articles: [article()], categories: [] })
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    await click('[data-test=option-note]')
    await type('[data-test=composer-body]', 'See: ')
    await click('[data-test=find-article]')
    await type('[data-test=article-search]', 'password')
    $('[data-test=article-search]').element.closest('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()
    await click('[data-test=insert-article-a1]')
    expect(($('[data-test=composer-body]').element as HTMLTextAreaElement).value).toBe(
      'See:\n\nClick "Forgot password".',
    )
    expect(exists('[data-test=article-results]')).toBe(false)
  })
})
