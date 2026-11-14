import { describe, expect, it } from 'vitest'
import RulesView from '@/modules/automation/views/RulesView.vue'
import WebhooksView from '@/modules/integrations/views/WebhooksView.vue'
import FollowQueueButton from '@/modules/notifications/components/FollowQueueButton.vue'
import NotificationBell from '@/modules/notifications/components/NotificationBell.vue'
import { useSession } from '@/modules/identity/session'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../support/fixtures'
import { queue } from '../support/helpdesk'
import { $, click, exists, flushPromises, mountView, testRouter, text, type } from '../support/mount'
import { spyToasts } from '../support/toasts'

const BASE = `/tenants/${TENANT_ID}`

function inTenant(): void {
  useSession().start(user())
  useTenants().put(tenant({ role: 'owner' }))
  useTenants().select(TENANT_ID)
}

describe('Following queues', () => {
  it('follows a queue from its inbox and stops again', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/notifications/queues`, { queues: [] })
      .on('PUT', `${BASE}/notifications/queues`, (request) => ({ body: request.body }))
    await mountView(FollowQueueButton, { props: { queueId: 'q1', queueName: 'Support' } })
    expect($('[data-test=follow-queue]').text()).toContain('Follow')

    await click('[data-test=follow-queue]')
    expect(fake.last('PUT', `${BASE}/notifications/queues`)?.body).toEqual({
      queues: [{ queue_id: 'q1', mode: 'new' }],
    })
    expect($('[data-test=follow-queue]').text()).toContain('Following')
    expect($('[data-test=follow-queue]').attributes('aria-pressed')).toBe('true')
    expect(toasts.success()).toContain('You now hear about new tickets in Support.')

    await click('[data-test=follow-queue]')
    expect(fake.last('PUT', `${BASE}/notifications/queues`)?.body).toEqual({ queues: [] })
    expect(toasts.success()).toContain('You no longer follow Support.')

    fake.error('PUT', `${BASE}/notifications/queues`, 422, 'invalid_followed_queues')
    await click('[data-test=follow-queue]')
    expect(toasts.error()).toHaveLength(1)
  })

  it('chooses how to follow each queue from the bell', async () => {
    inTenant()
    const items = [
      {
        id: 'n1',
        kind: 'created',
        ticket_id: 't1',
        ticket_number: 1001,
        subject: 'Printer broken',
        actor: 'carl@customer.example',
        created_at: '2026-11-13T12:00:00Z',
        read_at: null,
      },
      {
        id: 'n2',
        kind: 'moved',
        ticket_id: 't2',
        ticket_number: 1002,
        subject: 'Invoice',
        actor: 'bob@example.org',
        created_at: '2026-11-13T11:00:00Z',
        read_at: null,
      },
    ]
    const fake = new FakeApi()
      .json('GET', `${BASE}/notifications`, { items, unread: 2 })
      .json('GET', `${BASE}/me/notification-settings`, { email: false })
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .json('GET', `${BASE}/members`, [member()])
      .json('GET', `${BASE}/notifications/queues`, { queues: [{ queue_id: 'q2', mode: 'all' }] })
      .on('PUT', `${BASE}/notifications/queues`, (request) => ({ body: request.body }))
    await mountView(NotificationBell, { path: `/t/${TENANT_ID}/overview` })
    await click('[data-test=bell]')
    expect(text()).toContain('New ticket from carl@customer.example')
    expect(text()).toContain('bob@example.org moved it to a queue you follow')

    await click('[data-test=followed-queues]')
    expect(text()).toContain('Queues you follow')
    const billing = $('[data-test=follow-Billing] select').element as HTMLSelectElement
    expect(billing.value).toBe('all')
    await $('[data-test=follow-Support] select').setValue('new')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/notifications/queues`)?.body).toEqual({
      queues: [
        { queue_id: 'q2', mode: 'all' },
        { queue_id: 'q1', mode: 'new' },
      ],
    })
    await $('[data-test=follow-Billing] select').setValue('')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/notifications/queues`)?.body).toEqual({
      queues: [{ queue_id: 'q1', mode: 'new' }],
    })

    fake.error('PUT', `${BASE}/notifications/queues`, 422, 'invalid_followed_queues')
    await $('[data-test=follow-Billing] select').setValue('new')
    await flushPromises()
    expect(text()).toContain('You can only follow queues whose tickets you may see')
  })

  it('says so when there is no queue to follow', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/notifications`, { items: [], unread: 0 })
      .json('GET', `${BASE}/me/notification-settings`, { email: false })
      .json('GET', `${BASE}/queues`, [])
      .json('GET', `${BASE}/members`, [])
      .error('GET', `${BASE}/notifications/queues`, 500, 'internal_error')
    await mountView(NotificationBell, { path: `/t/${TENANT_ID}/overview` })
    await click('[data-test=bell]')
    await click('[data-test=followed-queues]')
    expect(text()).toContain('You cannot see any queue yet.')
    expect(exists('[data-test=error]')).toBe(true)
  })
})

describe('Alerts by e-mail in triggers', () => {
  it('sends alerts to the addresses given', async () => {
    inTenant()
    const trigger = {
      id: 't1',
      kind: 'trigger' as const,
      name: 'Alarm',
      active: true,
      position: 1,
      actions: {
        state: null,
        pending_hours: null,
        priority: null,
        queue_id: null,
        owner_id: null,
        owner_me: false,
        unassign: false,
        add_tags: [],
        remove_tags: [],
        note: '',
        reply: '',
        notify_emails: ['oncall@example.org'],
        notify_text: 'Look now',
      },
      event: 'created' as const,
      conditions: [{ field: 'queue_id' as const, operator: 'is' as const, value: 'q1' }],
      schedule: null,
      last_run_at: null,
    }
    const fake = new FakeApi()
      .json('GET', `${BASE}/triggers`, [trigger])
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [member()])
      .on('POST', `${BASE}/triggers`, (request) => ({ status: 201, body: { ...trigger, ...(request.body as object) } }))
      .on('PATCH', `${BASE}/triggers/t1`, (request) => ({ body: { ...trigger, ...(request.body as object) } }))
    const router = testRouter()
    router.addRoute({
      path: '/t/:tenantId/rules/triggers',
      name: 'rules-trigger',
      component: RulesView,
      meta: { kind: 'trigger' },
    })
    await mountView(RulesView, { router, path: `/t/${TENANT_ID}/rules/triggers` })
    expect($('[data-test=rule-Alarm]').text()).toContain('alert to oncall@example.org')

    await click('[data-test=edit-rule-Alarm]')
    expect(($('[data-test=notify-text]').element as HTMLTextAreaElement).value).toBe('Look now')
    await type('[data-test=notify-emails]', 'oncall@example.org; boss@example.org third@example.org')
    await click('[data-test=save-rule]')
    expect(fake.last('PATCH', `${BASE}/triggers/t1`)?.body).toMatchObject({
      actions: {
        notify_emails: ['oncall@example.org', 'boss@example.org', 'third@example.org'],
        notify_text: 'Look now',
      },
    })

    // Without addresses the text field goes away.
    await click('[data-test=create-rule]')
    await type('#rule-name', 'Quiet')
    expect(exists('[data-test=notify-text]')).toBe(false)
    await type('#action-note', 'x')
    await click('[data-test=save-rule]')
    expect(fake.last('POST', `${BASE}/triggers`)?.body).toMatchObject({
      actions: { notify_emails: [], notify_text: '' },
    })
  })
})

describe('Slack and Microsoft Teams webhooks', () => {
  const hook = {
    id: 'w1',
    name: 'Slack',
    url: 'https://hooks.slack.com/services/x',
    events: ['ticket.created'],
    active: true,
    format: 'slack',
    queue_ids: ['q2'],
    created_at: '2026-11-13T12:00:00Z',
    last_delivery_at: null,
    last_status: null,
    last_error: null,
    secret: null,
  }

  it('posts to chats, only for some queues', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/webhooks`, [hook, { ...hook, id: 'w2', name: 'All', format: 'json', queue_ids: [] }])
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .on('POST', `${BASE}/webhooks`, (request) => ({
        status: 201,
        body: { ...hook, id: 'w3', ...(request.body as object), secret: 'whsec_abc' },
      }))
      .on('PATCH', `${BASE}/webhooks/w1`, (request) => ({ body: { ...hook, ...(request.body as object) } }))
    await mountView(WebhooksView, { path: `/t/${TENANT_ID}/webhooks` })
    expect($('[data-test=webhook-Slack]').text()).toContain('Billing')
    expect($('[data-test=format-Slack]').text()).toBe('Slack')
    expect($('[data-test=webhook-All]').text()).toContain('all queues')
    expect(exists('[data-test=format-All]')).toBe(false)

    await click('[data-test=create-webhook]')
    await type('#webhook-name', 'Teams')
    await $('[data-test=format] select').setValue('teams')
    expect($('[data-test=format-hint]').text()).toContain('Send webhook alerts to a channel')
    await type('#webhook-url', 'https://prod.workflows.example/x')
    await click('[data-test=queue-Support] button')
    await click('[data-test=save-webhook]')
    expect(fake.last('POST', `${BASE}/webhooks`)?.body).toMatchObject({
      format: 'teams',
      queue_ids: ['q1'],
    })
    // Chats check no signature: no secret to show.
    expect(exists('[data-test=secret]')).toBe(false)

    await click('[data-test=edit-Slack]')
    expect(exists('[data-test=new-secret]')).toBe(false)
    await click('[data-test=queue-Billing] button')
    await click('[data-test=save-webhook]')
    expect(fake.last('PATCH', `${BASE}/webhooks/w1`)?.body).toMatchObject({ format: 'slack', queue_ids: [] })
  })

  it('shows a webhook of a queue it does not know', async () => {
    inTenant()
    new FakeApi().json('GET', `${BASE}/webhooks`, [hook]).error('GET', `${BASE}/queues`, 403, 'forbidden')
    await mountView(WebhooksView, { path: `/t/${TENANT_ID}/webhooks` })
    expect($('[data-test=webhook-Slack]').text()).toContain('?')
  })
})
