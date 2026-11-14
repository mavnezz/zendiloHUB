import { describe, expect, it, vi } from 'vitest'
import type { EmailAccount, MailFilter, QueueChannel, TextTemplate } from '@/modules/channels/api'
import EmailAccountsView from '@/modules/channels/views/EmailAccountsView.vue'
import FailedEmailsView from '@/modules/channels/views/FailedEmailsView.vue'
import MailFiltersView from '@/modules/channels/views/MailFiltersView.vue'
import MySignatureView from '@/modules/channels/views/MySignatureView.vue'
import QueueEmailView from '@/modules/channels/views/QueueEmailView.vue'
import TextTemplatesView from '@/modules/channels/views/TextTemplatesView.vue'
import { leaveTo } from '@/modules/channels/leave'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID } from '../../support/fixtures'
import { queue } from '../../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

vi.mock('@/modules/channels/leave', () => ({ leaveTo: vi.fn() }))

const BASE = `/tenants/${TENANT_ID}`
const PLACEHOLDERS = ['agent.name', 'customer.name', 'ticket.number']

function inTenant(): void {
  useTenants().put(tenant())
  useTenants().select(TENANT_ID)
}

function account(overrides: Partial<EmailAccount> = {}): EmailAccount {
  return {
    id: 'a1',
    name: 'Support',
    address: 'support@acme.example',
    display_name: 'Acme Support',
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
    last_fetch_at: '2026-11-13T12:00:00Z',
    last_error: null,
    failing_since: null,
    provider: null,
    needs_reconnect: false,
    created_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

function template(overrides: Partial<TextTemplate> = {}): TextTemplate {
  return {
    id: 's1',
    kind: 'signature',
    name: 'Standard',
    body: 'Best regards\n{{agent.name}}',
    updated_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

function filter(overrides: Partial<MailFilter> = {}): MailFilter {
  return {
    id: 'f1',
    account_id: null,
    name: 'Invoices',
    position: 1,
    active: true,
    match: 'all',
    conditions: [{ field: 'subject', operator: 'contains', value: 'invoice', header: '' }],
    actions: { queue_id: 'q1', priority: 'high', tags: ['billing'], ignore: false },
    stop: false,
    ...overrides,
  }
}

describe('EmailAccountsView', () => {
  it('adds, tests, fetches, edits and deletes accounts', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/email-accounts`, [
        account(),
        account({
          id: 'a2',
          address: 'billing@acme.example',
          display_name: '',
          last_error: 'The server did not answer',
          failing_since: '2026-11-13T11:00:00Z',
        }),
        account({ id: 'a3', address: 'old@acme.example', active: false }),
      ])
      .json('POST', `${BASE}/email-accounts`, account({ id: 'a4', address: 'sales@acme.example' }), 201)
      .json('PATCH', `${BASE}/email-accounts/a1`, account())
      .json('POST', `${BASE}/email-accounts/a1/test`, { imap: null, smtp: 'The server said: no' })
      .json('POST', `${BASE}/email-accounts/a2/test`, { imap: null, smtp: null })
      .on('POST', `${BASE}/email-accounts/a1/fetch`, { status: 202 })
      .on('DELETE', `${BASE}/email-accounts/a1`, { status: 204 })
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts` })
    expect($('[data-test="account-support@acme.example"]').text()).toContain('Acme Support <support@acme.example>')
    expect($('[data-test="account-billing@acme.example"] [data-test=last-error]').text()).toContain(
      'The server did not answer',
    )
    expect($('[data-test="account-old@acme.example"]').text()).toContain('paused')

    await click('[data-test=create-account]')
    await type('#account-address', 'sales@acme.example')
    expect(($('#imap-host').element as HTMLInputElement).value).toBe('imap.acme.example')
    expect(($('#smtp-username').element as HTMLInputElement).value).toBe('sales@acme.example')
    await type('#account-name', 'Sales')
    await type('#imap-password', 'secret')
    await click('[data-test=save-account]')
    expect(fake.last('POST', `${BASE}/email-accounts`)?.body).toEqual({
      name: 'Sales',
      address: 'sales@acme.example',
      display_name: '',
      queue_id: 'q1',
      folder: 'INBOX',
      active: true,
      imap: {
        host: 'imap.acme.example',
        port: 993,
        security: 'ssl',
        username: 'sales@acme.example',
        password: 'secret',
      },
      smtp: {
        host: 'smtp.acme.example',
        port: 587,
        security: 'starttls',
        username: 'sales@acme.example',
        password: null,
      },
    })
    expect(toasts.success()).toContain('sales@acme.example added.')

    await click('[data-test="edit-support@acme.example"]')
    expect(($('#imap-password').element as HTMLInputElement).placeholder).toBe('Leave empty to keep it')
    await type('#account-name', 'Help')
    await click('[data-test=save-account]')
    expect(fake.last('PATCH', `${BASE}/email-accounts/a1`)?.body).toMatchObject({
      name: 'Help',
      imap: { password: null },
    })

    await click('[data-test="test-support@acme.example"]')
    expect($('[data-test="probe-support@acme.example"]').text()).toContain('SMTP: The server said: no')
    await click('[data-test="test-billing@acme.example"]')
    expect(toasts.success()).toContain('Both servers accepted the login.')
    await click('[data-test="fetch-support@acme.example"]')
    expect(fake.calls('POST', `${BASE}/email-accounts/a1/fetch`)).toHaveLength(1)
    expect(toasts.success()).toContain('Fetching; new tickets appear within moments.')

    await click('[data-test="delete-support@acme.example"]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/email-accounts/a1`)).toHaveLength(1)
  })

  it('asks for a queue first and reports failures', async () => {
    const toasts = spyToasts()
    inTenant()
    new FakeApi().json('GET', `${BASE}/queues`, []).json('GET', `${BASE}/email-accounts`, [])
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts` })
    expect(text()).toContain('Create a queue first')

    new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/email-accounts`, [account()])
      .error('POST', `${BASE}/email-accounts/a1/test`, 404, 'account_not_found')
      .error('POST', `${BASE}/email-accounts/a1/fetch`, 404, 'account_not_found')
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts` })
    await click('[data-test="test-support@acme.example"]')
    await click('[data-test="fetch-support@acme.example"]')
    expect(toasts.error()).toEqual(['The e-mail account does not exist.', 'The e-mail account does not exist.'])

    new FakeApi().json('GET', `${BASE}/queues`, []).error('GET', `${BASE}/email-accounts`, 403, 'permission_denied')
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts` })
    expect(text()).toContain('Your role does not allow this.')
  })
})

describe('EmailAccountsView with OAuth', () => {
  const gmail = (overrides: Partial<EmailAccount> = {}) =>
    account({
      id: 'g1',
      address: 'help@gmail.example',
      provider: 'google',
      imap: { host: 'imap.gmail.com', port: 993, security: 'ssl', username: 'help@gmail.example', has_password: false },
      smtp: {
        host: 'smtp.gmail.com',
        port: 587,
        security: 'starttls',
        username: 'help@gmail.example',
        has_password: false,
      },
      ...overrides,
    })

  it('connects mailboxes at the configured providers', async () => {
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .json('GET', `${BASE}/email-accounts`, [
        gmail(),
        gmail({ id: 'g2', address: 'gone@gmail.example', needs_reconnect: true }),
      ])
      .json('GET', `${BASE}/email-accounts/oauth-providers`, { providers: ['microsoft'] })
      .json('POST', `${BASE}/email-accounts/oauth`, { url: 'https://login.microsoftonline.com/authorize?state=s' })
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts` })
    expect(exists('[data-test=connect-google]')).toBe(false)
    expect($('[data-test="account-help@gmail.example"] [data-test=provider]').text()).toBe('Connected with Google')
    expect($('[data-test="account-gone@gmail.example"] [data-test=needs-reconnect]').text()).toBe('reconnect needed')
    expect($('[data-test="account-help@gmail.example"]').text()).not.toContain('imap.gmail.com')

    await click('[data-test=connect-microsoft]')
    expect(text()).toContain('Connect Microsoft 365')
    await type('#connect-name', 'Outlook')
    await click('[data-test=start-connect]')
    expect(fake.last('POST', `${BASE}/email-accounts/oauth`)?.body).toEqual({
      provider: 'microsoft',
      name: 'Outlook',
      display_name: '',
      queue_id: 'q1',
    })
    expect(leaveTo).toHaveBeenLastCalledWith('https://login.microsoftonline.com/authorize?state=s')

    await click('[data-test="reconnect-gone@gmail.example"]')
    expect(fake.last('POST', `${BASE}/email-accounts/oauth`)?.body).toEqual({
      provider: 'google',
      account_id: 'g2',
      name: '',
      display_name: '',
    })

    // Editing keeps to what the provider does not fix.
    await click('[data-test="edit-help@gmail.example"]')
    expect($('[data-test=oauth-note]').text()).toContain('Connected with Google as help@gmail.example')
    expect(exists('#account-address')).toBe(false)
    expect(exists('#imap-host')).toBe(false)
  })

  it('reports how the provider sent the browser back', async () => {
    const toasts = spyToasts()
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/email-accounts`, [gmail()])
      .json('GET', `${BASE}/email-accounts/oauth-providers`, { providers: ['google'] })
      .json(
        'POST',
        `${BASE}/email-accounts/oauth`,
        { error: 'oauth_unavailable', message: 'no', params: { provider: 'google' } },
        422,
      )
    const { router } = await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts?connected=g1` })
    expect(toasts.success()).toContain('The mailbox is connected.')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})

    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts?oauth_error=expired` })
    await mountView(EmailAccountsView, { path: `/t/${TENANT_ID}/email-accounts?oauth_error=invalid_grant` })
    expect(toasts.error()).toEqual([
      'The mailbox could not be connected (the sign-in took too long or was used already).',
      'The mailbox could not be connected (invalid_grant).',
    ])

    await click('[data-test="reconnect-help@gmail.example"]')
    expect(toasts.error()).toContain('Connecting with google is not set up on this instance.')
    await click('[data-test=connect-google]')
    await click('[data-test=start-connect]')
    expect(text()).toContain('Connecting with google is not set up on this instance.')
  })
})

describe('QueueEmailView', () => {
  function api(settings: QueueChannel[] = []): FakeApi {
    return new FakeApi()
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .json('GET', `${BASE}/queue-channels`, settings)
      .json('GET', `${BASE}/email-accounts`, [account()])
      .json('GET', `${BASE}/text-templates`, {
        templates: [template(), template({ id: 's2', kind: 'salutation', name: 'Hello', body: 'Hi' })],
        placeholders: PLACEHOLDERS,
      })
      .on('PUT', /\/queue-channels\//, (request) => ({ body: request.body }))
  }

  it('sets the account, salutation, signature and auto reply of each queue', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api([
      {
        queue_id: 'q1',
        account_id: 'a1',
        signature_id: null,
        salutation_id: null,
        auto_reply: true,
        auto_reply_subject: 'Got it',
        auto_reply_body: 'Thanks',
        smime_sign: false,
        smime_encrypt: 'never',
      },
    ])
    await mountView(QueueEmailView, { path: `/t/${TENANT_ID}/queue-email` })
    expect($('[data-test=auto-q1]').text()).toContain('on')

    await $('[data-test=queue-q2] select[aria-label="Sends from"]').setValue('a1')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-channels/q2`)?.body).toMatchObject({ account_id: 'a1', auto_reply: false })
    expect(toasts.success()).toContain('Billing saved.')
    await $('[data-test=queue-q1] select[aria-label=Signature]').setValue('s1')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-channels/q1`)?.body).toMatchObject({ signature_id: 's1', account_id: 'a1' })
    await $('[data-test=queue-q1] select[aria-label=Salutation]').setValue('s2')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-channels/q1`)?.body).toMatchObject({ salutation_id: 's2' })
    await click('[data-test=sign-q1]')
    expect(fake.last('PUT', `${BASE}/queue-channels/q1`)?.body).toMatchObject({ smime_sign: true })
    await $('[data-test=queue-q1] select[aria-label=Encrypt]').setValue('always')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-channels/q1`)?.body).toMatchObject({ smime_encrypt: 'always' })

    await click('[data-test=auto-q2]')
    expect(($('#auto-subject').element as HTMLInputElement).value).toBe('Your request: {{ticket.subject}}')
    await click('[data-test=auto-on]')
    await click('[data-test="placeholder-ticket.number"]')
    await click('[data-test=save-auto]')
    const body = fake.last('PUT', `${BASE}/queue-channels/q2`)?.body as Record<string, unknown>
    expect(body.auto_reply).toBe(true)
    expect(String(body.auto_reply_body)).toMatch(/\{\{ticket\.number\}\}$/)
  })

  it('reports what the server refuses', async () => {
    const toasts = spyToasts()
    inTenant()
    api().error('PUT', /\/queue-channels\//, 422, 'invalid_template')
    await mountView(QueueEmailView, { path: `/t/${TENANT_ID}/queue-email` })
    await $('[data-test=queue-q1] select[aria-label="Sends from"]').setValue('a1')
    await flushPromises()
    expect(toasts.error()).toHaveLength(1)
    await click('[data-test=auto-q1]')
    await click('[data-test=save-auto]')
    expect($('[role=dialog] [data-test=error]').text()).toContain('Please check the text')
  })
})

describe('TextTemplatesView', () => {
  it('creates, edits and deletes signatures and salutations', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/text-templates`, { templates: [template()], placeholders: PLACEHOLDERS })
      .json('POST', `${BASE}/text-templates`, template({ id: 's3', kind: 'salutation', name: 'Hi' }), 201)
      .json('PATCH', `${BASE}/text-templates/s1`, template({ name: 'Short' }))
      .on('DELETE', `${BASE}/text-templates/s1`, { status: 204 })
    await mountView(TextTemplatesView, { path: `/t/${TENANT_ID}/text-templates` })
    expect($('[data-test=kind-salutation]').text()).toContain('None yet.')
    expect($('[data-test=template-Standard]').text()).toContain('{{agent.name}}')

    await click('[data-test=create-salutation]')
    await type('#template-name', 'Hi')
    await type('#template-body', 'Hello')
    await click('[data-test="placeholder-customer.name"]')
    await click('[data-test=save-template]')
    expect(fake.last('POST', `${BASE}/text-templates`)?.body).toEqual({
      kind: 'salutation',
      name: 'Hi',
      body: 'Hello {{customer.name}}',
    })
    expect(toasts.success()).toContain('"Hi" saved.')

    await click('[data-test=edit-Standard]')
    await type('#template-name', 'Short')
    await click('[data-test=save-template]')
    expect(fake.last('PATCH', `${BASE}/text-templates/s1`)?.body).toMatchObject({ kind: 'signature', name: 'Short' })

    await click('[data-test=delete-Standard]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/text-templates/s1`)).toHaveLength(1)

    fake.error('POST', `${BASE}/text-templates`, 422, 'invalid_template')
    await click('[data-test=create-signature]')
    await click('[data-test="placeholder-agent.name"]')
    await type('#template-name', 'X')
    await click('[data-test=save-template]')
    expect(text()).toContain('Please check the text')
  })
})

describe('MailFiltersView', () => {
  it('creates, edits, reorders and deletes filters', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/mail-filters`, [
        filter(),
        filter({
          id: 'f2',
          name: 'Spam',
          match: 'any',
          stop: true,
          active: false,
          conditions: [
            { field: 'header', header: 'X-Spam-Flag', operator: 'equals', value: 'yes' },
            { field: 'from', header: '', operator: 'ends_with', value: '@spam.example' },
          ],
          actions: { queue_id: null, priority: null, tags: [], ignore: true },
        }),
      ])
      .json('POST', `${BASE}/mail-filters`, filter({ id: 'f3', name: 'VIP' }), 201)
      .json('PATCH', `${BASE}/mail-filters/f2`, filter())
      .json('PUT', `${BASE}/mail-filters-order`, [filter({ id: 'f2', name: 'Spam' }), filter()])
      .on('DELETE', `${BASE}/mail-filters/f1`, { status: 204 })
    await mountView(MailFiltersView, { path: `/t/${TENANT_ID}/mail-filters` })
    expect($('[data-test=filter-Invoices]').text()).toContain(
      'Subject contains „invoice“ → to Support · Priority: High · #billing',
    )
    expect($('[data-test=filter-Spam]').text()).toContain(
      'X-Spam-Flag is „yes“ or Sender ends with „@spam.example“ → dropped',
    )

    await click('[data-test=create-filter]')
    await type('#filter-name', 'VIP')
    await $('[data-test=condition-0] input[aria-label=Value]').setValue('ceo@')
    await click('[data-test=add-condition]')
    await $('[data-test=condition-1] select[aria-label=Field]').setValue('header')
    await $('[data-test=condition-1] input[aria-label=Header]').setValue('X-Priority')
    await $('[data-test=condition-1] input[aria-label=Value]').setValue('1')
    await $('#filter-priority').setValue('urgent')
    await type('#filter-tags', 'vip, boss')
    await click('[data-test=filter-stop]')
    await click('[data-test=save-filter]')
    expect(fake.last('POST', `${BASE}/mail-filters`)?.body).toEqual({
      name: 'VIP',
      active: true,
      match: 'all',
      stop: true,
      conditions: [
        { field: 'subject', operator: 'contains', value: 'ceo@', header: '' },
        { field: 'header', operator: 'contains', value: '1', header: 'X-Priority' },
      ],
      actions: { queue_id: null, priority: 'urgent', tags: ['vip', 'boss'], ignore: false },
      account_id: null,
    })
    expect(toasts.success()).toContain('Filter "VIP" saved.')

    await click('[data-test=edit-Spam]')
    expect(($('[data-test=condition-0] input[aria-label=Header]').element as HTMLInputElement).value).toBe(
      'X-Spam-Flag',
    )
    await click('[data-test=save-filter]')
    expect(fake.last('PATCH', `${BASE}/mail-filters/f2`)?.body).toMatchObject({
      match: 'any',
      actions: { ignore: true, tags: [] },
    })

    await click('[data-test=up-Spam]')
    expect(fake.last('PUT', `${BASE}/mail-filters-order`)?.body).toEqual({ filter_ids: ['f2', 'f1'], account_id: null })

    await click('[data-test=delete-Invoices]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/mail-filters/f1`)).toHaveLength(1)
  })

  it('shows an empty list and failures', async () => {
    const toasts = spyToasts()
    inTenant()
    new FakeApi().json('GET', `${BASE}/queues`, []).json('GET', `${BASE}/mail-filters`, [])
    await mountView(MailFiltersView, { path: `/t/${TENANT_ID}/mail-filters` })
    expect(text()).toContain('No filters yet')

    new FakeApi()
      .json('GET', `${BASE}/queues`, [])
      .json('GET', `${BASE}/mail-filters`, [filter(), filter({ id: 'f2', name: 'Two' })])
      .error('PUT', `${BASE}/mail-filters-order`, 404, 'filter_not_found')
    await mountView(MailFiltersView, { path: `/t/${TENANT_ID}/mail-filters` })
    expect($('[data-test=filter-Invoices]').text()).toContain('to ?')
    await click('[data-test=up-Two]')
    expect(toasts.error()).toContain('The filter does not exist.')
  })
})

describe('FailedEmailsView and MySignatureView', () => {
  it('processes failed e-mails again or deletes them', async () => {
    const toasts = spyToasts()
    inTenant()
    const failed = {
      id: 'x1',
      account_id: 'a1',
      error: 'ValueError: The e-mail has no sender',
      received_at: '2026-11-13T12:00:00Z',
      subject: 'Hello',
      sender: '',
      size: 2048,
    }
    const fake = new FakeApi()
      .json('GET', `${BASE}/failed-emails`, [failed, { ...failed, id: 'x2', subject: '' }])
      .json('POST', `${BASE}/failed-emails/x1/retry`, { outcome: 'created' })
      .json('POST', `${BASE}/failed-emails/x2/retry`, { outcome: 'failed' })
      .on('DELETE', `${BASE}/failed-emails/x1`, { status: 204 })
    await mountView(FailedEmailsView, { path: `/t/${TENANT_ID}/failed-emails` })
    expect($$('[data-test=failed-email]')[0]?.text()).toContain('2 KB')
    await click('[data-test=retry-x1]')
    expect(toasts.success()).toContain('A ticket was opened.')
    await click('[data-test=retry-x2]')
    expect(toasts.error()).toContain('It failed again; it is listed once more.')
    await click('[data-test=delete-x1]')
    expect(fake.calls('DELETE', `${BASE}/failed-emails/x1`)).toHaveLength(1)
    expect(toasts.success()).toContain('E-mail deleted.')

    fake.error('DELETE', `${BASE}/failed-emails/x2`, 404, 'failed_email_not_found')
    fake.error('POST', `${BASE}/failed-emails/x2/retry`, 404, 'failed_email_not_found')
    await click('[data-test=delete-x2]')
    await click('[data-test=retry-x2]')
    expect(toasts.error()).toContain('The e-mail does not exist any more.')

    new FakeApi().json('GET', `${BASE}/failed-emails`, [])
    await mountView(FailedEmailsView, { path: `/t/${TENANT_ID}/failed-emails` })
    expect(text()).toContain('No failed e-mails.')
  })

  it('saves the personal signature', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/me/email-settings`, { name: 'Ada', title: '', signature: '' })
      .on('PUT', `${BASE}/me/email-settings`, (request) => ({ body: request.body }))
    await mountView(MySignatureView, { path: `/t/${TENANT_ID}/my-signature` })
    expect(($('#personal-name').element as HTMLInputElement).value).toBe('Ada')
    await type('#personal-title', 'Support')
    await type('#personal-signature', 'Tel. 123')
    await click('[data-test=save-personal]')
    expect(fake.last('PUT', `${BASE}/me/email-settings`)?.body).toEqual({
      name: 'Ada',
      title: 'Support',
      signature: 'Tel. 123',
    })
    expect(toasts.success()).toContain('Saved.')

    fake.error('PUT', `${BASE}/me/email-settings`, 422, 'invalid_template')
    await click('[data-test=save-personal]')
    expect(exists('[data-test=error]')).toBe(true)
    new FakeApi().error('GET', `${BASE}/me/email-settings`, 500, 'internal_error')
    await mountView(MySignatureView, { path: `/t/${TENANT_ID}/my-signature` })
    expect(exists('[data-test=error]')).toBe(true)
  })
})
