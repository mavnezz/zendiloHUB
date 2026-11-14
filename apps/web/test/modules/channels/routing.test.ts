import { describe, expect, it } from 'vitest'
import type { EmailAccount, FilterTest, MailFilter } from '@/modules/channels/api'
import EmailAccountsView from '@/modules/channels/views/EmailAccountsView.vue'
import MailFiltersView from '@/modules/channels/views/MailFiltersView.vue'
import QueueEmailView from '@/modules/channels/views/QueueEmailView.vue'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID } from '../../support/fixtures'
import { queue } from '../../support/helpdesk'
import { $, $$, click, exists, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const BASE = `/tenants/${TENANT_ID}`

function inTenant(): void {
  useTenants().put(tenant())
  useTenants().select(TENANT_ID)
}

function account(overrides: Partial<EmailAccount> = {}): EmailAccount {
  return {
    id: 'a1',
    name: 'Support',
    address: 'support@acme.example',
    display_name: '',
    queue_id: 'q1',
    imap: {
      host: 'imap.acme.example',
      port: 993,
      security: 'ssl',
      username: 'support@acme.example',
      has_password: true,
    },
    smtp: {
      host: 'smtp.acme.example',
      port: 587,
      security: 'starttls',
      username: 'support@acme.example',
      has_password: true,
    },
    folder: 'INBOX',
    active: true,
    last_fetch_at: null,
    last_error: null,
    failing_since: null,
    provider: null,
    needs_reconnect: false,
    created_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

function filter(overrides: Partial<MailFilter> = {}): MailFilter {
  return {
    id: 'f1',
    account_id: null,
    name: 'Spam',
    position: 1,
    active: true,
    match: 'all',
    conditions: [{ field: 'subject', operator: 'contains', value: 'viagra', header: '' }],
    actions: { queue_id: null, priority: null, tags: [], ignore: true },
    stop: false,
    ...overrides,
  }
}

function trace(overrides: Partial<FilterTest> = {}): FilterTest {
  return {
    matched: [],
    stopped: false,
    ignore: false,
    queue_id: null,
    priority: null,
    tags: [],
    default_queue_id: 'q1',
    final_queue_id: 'q1',
    checked: 1,
    ...overrides,
  }
}

const billing = filter({
  id: 'r1',
  name: 'Billing',
  account_id: 'a1',
  stop: true,
  actions: { queue_id: 'q2', priority: null, tags: [], ignore: false },
})

describe('MailFiltersView with mailbox rules', () => {
  it('groups the filters by scope and tests where an e-mail goes', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .json('GET', `${BASE}/email-accounts`, [account(), account({ id: 'a2', address: 'sales@acme.example' })])
      .json('GET', `${BASE}/mail-filters`, [filter(), billing])
      .json('POST', `${BASE}/mail-filters/test`, {
        ...trace({ matched: [filter(), billing], stopped: true, queue_id: 'q2', final_queue_id: 'q2', checked: 2 }),
        priority: 'high',
        tags: ['billing'],
      })
    await mountView(MailFiltersView, { path: `/t/${TENANT_ID}/mail-filters` })
    expect($('[data-test=scope-all]').text()).toContain('All mailboxes')
    expect($('[data-test="scope-support@acme.example"]').text()).toContain('Rules of support@acme.example')
    expect($('[data-test="scope-support@acme.example"]').text()).toContain('1. Billing')
    expect(exists('[data-test="scope-sales@acme.example"]')).toBe(false)

    await click('[data-test=edit-Billing]')
    expect(($('#filter-scope').element as HTMLSelectElement).value).toBe('a1')

    await click('[data-test=test-filters]')
    await $('[data-test=test-raw]').setValue('Subject: Invoice')
    await click('[data-test=run-test]')
    expect(fake.last('POST', `${BASE}/mail-filters/test`)?.body).toEqual({ raw: 'Subject: Invoice', account_id: 'a1' })
    const result = $('[data-test=test-result]').text()
    expect(result).toContain('2 active filters ran.')
    expect(result).toContain('Rules of support@acme.example')
    expect(result).toContain('A filter ended the run')
    expect(result).toContain('Into the queue Billing (by a filter)')
    expect(result).toContain('#billing')
  })

  it('tells the default queue, dropped mail, no queue and failures', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/email-accounts`, [account()])
      .json('GET', `${BASE}/mail-filters`, [filter()])
      .json('POST', `${BASE}/mail-filters/test`, trace())
    await mountView(MailFiltersView, { path: `/t/${TENANT_ID}/mail-filters` })
    await click('[data-test=test-filters]')
    await $('[data-test=test-raw]').setValue('Subject: Hi')
    await click('[data-test=run-test]')
    expect($('[data-test=test-result]').text()).toContain('No filter matches.')
    expect($('[data-test=test-queue]').text()).toContain('Into the queue Support (the default queue of the mailbox)')

    fake.json(
      'POST',
      `${BASE}/mail-filters/test`,
      trace({ matched: [filter()], stopped: true, ignore: true, default_queue_id: null, final_queue_id: null }),
    )
    await $('#test-account').setValue('')
    await click('[data-test=run-test]')
    expect(fake.last('POST', `${BASE}/mail-filters/test`)?.body).toMatchObject({ account_id: null })
    expect($('[data-test=test-dropped]').text()).toContain('would be dropped')
    expect($('[data-test=test-result]').text()).toContain('All mailboxes')

    fake.json('POST', `${BASE}/mail-filters/test`, trace({ default_queue_id: null, final_queue_id: null }))
    await click('[data-test=run-test]')
    expect($('[data-test=test-queue]').text()).toContain('No queue')

    fake.error('POST', `${BASE}/mail-filters/test`, 404, 'account_not_found')
    await click('[data-test=run-test]')
    expect(text()).toContain('The e-mail account does not exist.')
  })
})

describe('EmailAccountsView with the way of the mail', () => {
  it('shows each mailbox with its rules and default queue', async () => {
    const toasts = spyToasts()
    inTenant()
    const rules = [billing, filter({ id: 'r2', name: 'Urgent', account_id: 'a1', position: 2 })]
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .json('GET', `${BASE}/email-accounts`, [
        account(),
        account({ id: 'a2', address: 'alerts@acme.example', smtp: null }),
      ])
      .json('GET', `${BASE}/mail-filters`, [filter(), ...rules])
      .json('GET', `${BASE}/email-accounts/oauth-providers`, { providers: [] })
      .json('POST', `${BASE}/mail-filters`, filter({ id: 'r3', name: 'VIP', account_id: 'a1' }), 201)
      .json('PUT', `${BASE}/mail-filters-order`, rules)
      .json('POST', `${BASE}/email-accounts/a2/test`, { imap: null, smtp: null })
      .json('PATCH', `${BASE}/email-accounts/a2`, account({ id: 'a2', smtp: null }))
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts` })
    const flow = $('[data-test="flow-support@acme.example"]').text()
    expect(flow).toContain('Incoming via support@acme.example')
    expect(flow).toContain('first the filters for all mailboxes (1)')
    expect(flow).toContain('then the rules of this mailbox, top to bottom (2)')
    expect(flow).toContain('1. Billing')
    expect(flow).toContain('2. Urgent')
    expect($('[data-test="default-support@acme.example"]').text()).toContain('otherwise into the queue Support')
    expect($('[data-test="flow-alerts@acme.example"]').text()).toContain('no rules of its own')
    expect($('[data-test="account-alerts@acme.example"] [data-test=incoming-only]').text()).toBe('incoming only')

    await click('[data-test="account-support@acme.example"] [data-test=down-Billing]')
    expect(fake.last('PUT', `${BASE}/mail-filters-order`)?.body).toEqual({ filter_ids: ['r2', 'r1'], account_id: 'a1' })

    await click('[data-test="add-rule-support@acme.example"]')
    expect(($('#filter-scope').element as HTMLSelectElement).value).toBe('a1')
    await type('#filter-name', 'VIP')
    await $('[data-test=condition-0] input[aria-label=Value]').setValue('ceo')
    await $('#filter-queue').setValue('q1')
    await click('[data-test=save-filter]')
    expect(fake.last('POST', `${BASE}/mail-filters`)?.body).toMatchObject({ account_id: 'a1', stop: true })
    expect(toasts.success()).toContain('Filter "VIP" saved.')

    await click('[data-test="test-rules-alerts@acme.example"]')
    expect(($('#test-account').element as HTMLSelectElement).value).toBe('a2')

    await click('[data-test="test-alerts@acme.example"]')
    expect($('[data-test="probe-alerts@acme.example"]').text()).not.toContain('SMTP')

    await click('[data-test="edit-alerts@acme.example"]')
    expect(exists('#smtp-host')).toBe(false)
    await click('[data-test=account-sends]')
    expect(exists('#smtp-host')).toBe(true)
    await click('[data-test=account-sends]')
    await click('[data-test=save-account]')
    expect(fake.last('PATCH', `${BASE}/email-accounts/a2`)?.body).toMatchObject({ smtp: null })
  })
})

describe('QueueEmailView with incoming mailboxes', () => {
  it('lists the incoming mailboxes of each queue and only sending ones to send with', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/queue-channels`, [])
      .json('GET', `${BASE}/email-accounts`, [
        account(),
        account({ id: 'a2', address: 'alerts@acme.example', smtp: null }),
      ])
      .json('GET', `${BASE}/text-templates`, { templates: [], placeholders: [] })
    await mountView(QueueEmailView, { path: `/t/${TENANT_ID}/queue-email` })
    expect($('[data-test=incoming-q1]').text()).toBe('support@acme.example, alerts@acme.example')
    expect($('[data-test=fallback-q1]').text()).toContain('Replies go out by the mailbox the ticket came in by.')
    const options = $$('[data-test=queue-q1] select')[0]!
      .findAll('option')
      .map((each) => each.text())
    expect(options).toEqual(['Mailbox of the ticket', 'support@acme.example'])
  })
})
