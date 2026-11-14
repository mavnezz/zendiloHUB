import { describe, expect, it } from 'vitest'
import type { Delivery, SmimeCertificate } from '@/modules/channels/api'
import SmimeView from '@/modules/channels/views/SmimeView.vue'
import { useTenants } from '@/modules/tenancy/tenants'
import MessageList from '@/modules/tickets/components/MessageList.vue'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID } from '../../support/fixtures'
import { message } from '../../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const BASE = `/tenants/${TENANT_ID}`
const DAY = 24 * 60 * 60 * 1000

function certificate(overrides: Partial<SmimeCertificate> = {}): SmimeCertificate {
  return {
    id: 'c1',
    kind: 'own',
    subject: 'CN=support@acme.example',
    issuer: 'CN=Test CA',
    serial: '1f',
    emails: ['support@acme.example'],
    not_before: '2026-01-01T00:00:00Z',
    not_after: new Date(Date.now() + 365 * DAY).toISOString(),
    fingerprint: 'ab'.repeat(32),
    has_key: true,
    created_at: '2026-11-14T12:00:00Z',
    ...overrides,
  }
}

function inTenant(): void {
  useTenants().put(tenant())
  useTenants().select(TENANT_ID)
}

async function pick(selector: string, file: File): Promise<void> {
  const input = $(selector)
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('SmimeView', () => {
  it('lists, adds and deletes certificates of each kind', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/smime/certificates`, [
        certificate(),
        certificate({
          id: 'c2',
          kind: 'contact',
          emails: ['carl@customer.example'],
          has_key: false,
          not_after: new Date(Date.now() + 5 * DAY).toISOString(),
        }),
        certificate({ id: 'c3', kind: 'ca', emails: [], subject: 'CN=Test CA', has_key: false }),
        certificate({
          id: 'c4',
          kind: 'contact',
          emails: ['old@customer.example'],
          has_key: false,
          not_after: '2025-01-01T00:00:00Z',
        }),
      ])
      .json('POST', `${BASE}/smime/certificates`, certificate({ id: 'c5' }), 201)
      .on('DELETE', `${BASE}/smime/certificates/c2`, { status: 204 })
    await mountView(SmimeView, { path: `/t/${TENANT_ID}/smime` })
    expect($$('[data-test=certificate]')).toHaveLength(1)
    expect(text()).toContain('with key')
    expect(exists('[data-test=validity-c1]')).toBe(false)

    // Our certificate as a PKCS #12 file with its password.
    await click('[data-test=add-certificate]')
    expect($('[data-test=save-certificate]').attributes('disabled')).toBeDefined()
    await pick('[data-test=certificate-file]', new File(['p12'], 'support.p12'))
    await type('[data-test=certificate-password]', 'secret')
    await click('[data-test=save-certificate]')
    const form = fake.last('POST', `${BASE}/smime/certificates`)?.body as FormData
    expect([form.get('kind'), form.get('password'), (form.get('file') as File).name]).toEqual([
      'own',
      'secret',
      'support.p12',
    ])
    expect(form.get('key')).toBeNull()
    expect(toasts.success()).toContain('Certificate of support@acme.example added.')

    // Contacts: one expires soon, one has expired.
    await click('[data-test=option-contact]')
    expect($$('[data-test=certificate]')).toHaveLength(2)
    expect($('[data-test=validity-c2]').text()).toBe('expires soon')
    expect($('[data-test=validity-c4]').text()).toBe('expired')
    await click('[data-test=add-certificate]')
    expect(exists('[data-test=certificate-password]')).toBe(false)
    await click('[data-test=delete-c2]')
    expect(text()).toContain('Delete the certificate of carl@customer.example?')
    await click('[role=alertdialog] button:last-child')
    expect(fake.calls('DELETE', `${BASE}/smime/certificates/c2`)).toHaveLength(1)
    expect(toasts.success()).toContain('Certificate deleted.')

    await click('[data-test=option-ca]')
    expect(text()).toContain('CN=Test CA')
  })

  it('sends a certificate with its key and explains refusals', async () => {
    inTenant()
    const fake = new FakeApi().json('GET', `${BASE}/smime/certificates`, []).on('POST', `${BASE}/smime/certificates`, {
      status: 422,
      body: { error: 'invalid_certificate', message: 'x', params: { field: 'key_mismatch' } },
    })
    await mountView(SmimeView, { path: `/t/${TENANT_ID}/smime` })
    expect(text()).toContain('No certificates yet')
    await click('[data-test=add-certificate]')
    await pick('[data-test=certificate-file]', new File(['cert'], 'support.pem'))
    await pick('[data-test=certificate-key]', new File(['key'], 'support.key'))
    await click('[data-test=save-certificate]')
    const form = fake.last('POST', `${BASE}/smime/certificates`)?.body as FormData
    expect((form.get('key') as File).name).toBe('support.key')
    expect($('[role=dialog] [data-test=error]').text()).toContain('does not belong to the certificate')
  })
})

describe('MessageList', () => {
  it('shows what S/MIME said about a mail and why a reply was not sent', async () => {
    const failed: Delivery = {
      message_id: 'm3',
      status: 'failed',
      error: 'smime_no_certificate',
      attempts: 0,
      updated_at: '2026-11-14T12:00:00Z',
    }
    await mountView(MessageList, {
      props: {
        messages: [
          message({
            id: 'm1',
            security: { signed: true, signature: 'valid', signer: 'carl@customer.example', encrypted: true },
          }),
          message({
            id: 'm2',
            security: { signed: true, signature: 'invalid', signer: null, encrypted: false },
          }),
          message({ id: 'm3', direction: 'out', author_kind: 'agent' }),
          message({ id: 'm4', security: { signed: false, signature: null, signer: null, encrypted: true } }),
        ],
        customer: null,
        canSplit: false,
        deliveries: { m3: failed },
      },
    })
    await flushPromises()
    expect($('[data-test=security-m1]').text()).toBe('Signed · validEncrypted')
    expect($('[data-test=security-m1]').attributes('title')).toBe('S/MIME, signed by carl@customer.example')
    expect($('[data-test=security-m2]').text()).toBe('Signature invalid')
    expect($('[data-test=security-m2]').attributes('title')).toBe('S/MIME')
    expect($('[data-test=security-m4]').text()).toBe('Encrypted')
    expect($('[data-test=delivery-m3]').text()).toContain("the customer's S/MIME certificate is missing")
  })
})
