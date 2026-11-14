import { describe, expect, it } from 'vitest'
import PortalHomeView from '@/modules/portal/views/PortalHomeView.vue'
import PortalTicketView from '@/modules/portal/views/PortalTicketView.vue'
import { useSession } from '@/modules/identity/session'
import { useTenants } from '@/modules/tenancy/tenants'
import TicketView from '@/modules/tickets/views/TicketView.vue'
import { FakeApi } from '../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../support/fixtures'
import { detail, message, queue } from '../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, type } from '../support/mount'
import { spyToasts } from '../support/toasts'

const BASE = `/tenants/${TENANT_ID}`
const PORTAL = `/portal/${TENANT_ID}`

function attachment(id: string, filename: string, content_type = 'application/pdf') {
  return { id, filename, content_type, size: 1536, inline: content_type.startsWith('image/'), created_at: '' }
}

function inTenant(): void {
  useSession().start(user())
  useTenants().put(tenant({ role: 'owner' }))
  useTenants().select(TENANT_ID)
}

function desk(): FakeApi {
  return new FakeApi()
    .json('GET', `${BASE}/queues`, [queue()])
    .json('GET', `${BASE}/members`, [member()])
    .json('GET', `${BASE}/tickets/t1`, detail())
    .json('GET', `${BASE}/tickets/t1/messages`, [
      message({ attachments: [attachment('a1', 'invoice.pdf'), attachment('a2', 'photo.png', 'image/png')] }),
    ])
    .json('GET', `${BASE}/tickets/t1/history`, [])
}

/** Picks files in a hidden file input, as the browser's dialog would. */
async function pick(selector: string, files: File[]): Promise<void> {
  const input = $(selector)
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

const file = (name: string, type = 'text/plain') => new File(['content'], name, { type })

describe('attachments in a ticket', () => {
  it('shows the files of messages with links and previews', async () => {
    inTenant()
    desk()
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    const links = $$('[data-test=message-public-in] a').map((link) => link.attributes('href'))
    expect(links).toEqual([`/api/v1${BASE}/tickets/t1/attachments/a1`, `/api/v1${BASE}/tickets/t1/attachments/a2`])
    expect($('[data-test="file-invoice.pdf"]').text()).toContain('1.5 KB')
    expect($('[data-test="file-invoice.pdf"] a').attributes('download')).toBe('invoice.pdf')
    expect($('[data-test="file-photo.png"] img').attributes('src')).toBe(`/api/v1${BASE}/tickets/t1/attachments/a2`)
  })

  it('uploads, takes back and sends files with a reply', async () => {
    inTenant()
    const toasts = spyToasts()
    let uploads = 0
    const fake = desk()
      .on('POST', `${BASE}/tickets/t1/attachments`, () => {
        uploads++
        return uploads === 3
          ? { status: 413, body: { error: 'attachment_too_large', message: 'x', params: { max_mb: 25 } } }
          : { status: 201, body: attachment(`u${uploads}`, uploads === 1 ? 'log.txt' : 'shot.png', 'text/plain') }
      })
      .on('DELETE', `${BASE}/tickets/t1/attachments/u2`, { status: 204 })
      .json('POST', `${BASE}/tickets/t1/messages`, message(), 201)
    await mountView(TicketView, { path: `/t/${TENANT_ID}/tickets/t1` })
    // The reply starts empty here (no queue draft): only files may go out too.
    expect($('[data-test=send]').attributes('disabled')).toBeDefined()

    await pick('[data-test=file-input]', [file('log.txt'), file('shot.png', 'image/png')])
    expect(fake.calls('POST', `${BASE}/tickets/t1/attachments`)).toHaveLength(2)
    expect((fake.last('POST', `${BASE}/tickets/t1/attachments`)!.body as FormData).get('file')).toBeInstanceOf(File)
    expect($$('[data-test=composer] [data-test^=file-]').map((chip) => chip.attributes('data-test'))).toEqual([
      'file-chips',
      'file-log.txt',
      'file-shot.png',
      'file-input',
    ])
    await click('[data-test="remove-file-shot.png"]')
    expect(fake.calls('DELETE', `${BASE}/tickets/t1/attachments/u2`)).toHaveLength(1)

    // Dropped files go up the same way; a refused one disappears with a message.
    const form = $('[data-test=composer]')
    await form.trigger('dragover')
    expect(form.classes()).toContain('border-primary')
    await form.trigger('drop', { dataTransfer: { files: [file('huge.zip')] } })
    await flushPromises()
    expect(toasts.error()).toEqual(['A file may have at most 25 MB.'])
    expect(exists('[data-test="file-huge.zip"]')).toBe(false)

    expect($('[data-test=send]').attributes('disabled')).toBeUndefined()
    await click('[data-test=send]')
    expect(fake.last('POST', `${BASE}/tickets/t1/messages`)!.body).toMatchObject({ body: '', attachment_ids: ['u1'] })
    expect(exists('[data-test=composer] [data-test=file-chips]')).toBe(false)
  })
})

const THREAD = {
  ticket: {
    id: 't1',
    number: 1001,
    subject: 'Printer broken',
    state: 'open' as const,
    created_at: '2026-11-13T12:00:00Z',
    updated_at: '2026-11-14T09:00:00Z',
  },
  messages: [
    {
      id: 'm1',
      from_customer: false,
      author_name: 'Ada',
      body: '',
      attachments: [{ id: 'f1', filename: 'manual.pdf', content_type: 'application/pdf', size: 10 }],
      created_at: '2026-11-13T12:00:00Z',
    },
  ],
}

describe('attachments in the portal', () => {
  it('sends up to five files with a reply', async () => {
    const fake = new FakeApi()
      .json('GET', `${PORTAL}/tickets/t1`, THREAD)
      .json('POST', `${PORTAL}/tickets/t1/messages`, THREAD)
    await mountView(PortalTicketView, { path: `/portal/${TENANT_ID}/tickets/t1` })
    expect($('[data-test=portal-message-m1]').text()).toContain('manual.pdf')
    expect($('[data-test=portal-answer]').attributes('disabled')).toBeDefined()

    await pick(
      '[data-test=portal-file-input]',
      [1, 2, 3, 4, 5, 6].map((n) => file(`${n}.txt`)),
    )
    expect($$('form [data-test^="file-"][data-test$=".txt"]')).toHaveLength(5)
    expect($('[data-test=portal-attach]').attributes('disabled')).toBeDefined()
    await click('[data-test="remove-file-1.txt"]')
    expect(exists('[data-test="file-1.txt"]')).toBe(false)

    await click('[data-test=portal-answer]')
    const sent = fake.last('POST', `${PORTAL}/tickets/t1/messages`)!.body as FormData
    expect(sent.get('body')).toBe('')
    expect((sent.getAll('files') as File[]).map((each) => each.name)).toEqual(['2.txt', '3.txt', '4.txt', '5.txt'])
    expect(exists('form [data-test=file-chips]')).toBe(false)
  })

  it('sends files with a new request', async () => {
    const fake = new FakeApi()
      .json('GET', `${PORTAL}/me`, { name: 'Carl', email: 'c@x', company_name: null, company_tickets: false })
      .json('GET', `${PORTAL}/tickets`, [])
      .json('POST', `${PORTAL}/tickets`, { ...THREAD.ticket, id: 't3' }, 201)
    await mountView(PortalHomeView, { path: `/portal/${TENANT_ID}` })
    await click('[data-test=portal-new]')
    await type('[data-test=portal-subject]', 'Broken screen')
    await type('[data-test=portal-body]', 'See photo')
    await pick('[data-test=portal-new-file-input]', [file('screen.jpg', 'image/jpeg'), file('log.txt')])
    await click('[data-test="remove-file-log.txt"]')
    await click('[data-test=portal-submit]')
    const sent = fake.last('POST', `${PORTAL}/tickets`)!.body as FormData
    expect((sent.getAll('files') as File[]).map((each) => each.name)).toEqual(['screen.jpg'])
  })
})
