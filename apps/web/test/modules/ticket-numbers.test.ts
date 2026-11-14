import { describe, expect, it } from 'vitest'
import { useSession } from '@/modules/identity/session'
import { useTenants } from '@/modules/tenancy/tenants'
import TicketNumbersView from '@/modules/tickets/views/TicketNumbersView.vue'
import { FakeApi } from '../support/fake-api'
import { tenant, TENANT_ID, user } from '../support/fixtures'
import { $, click, mountView, text } from '../support/mount'
import { spyToasts } from '../support/toasts'

const PATH = `/tenants/${TENANT_ID}/ticket-numbers`
const SAVED = {
  format: 'increment' as const,
  start: 1001,
  date_digits: 4,
  checksum: false,
  prefix: '#',
  next_number: 1042,
  next_tag: '[#1042]',
}

function inTenant(): void {
  useSession().start(user())
  useTenants().put(tenant({ role: 'owner' }))
  useTenants().select(TENANT_ID)
}

function preview(): string {
  return $('[data-test=preview]').text()
}

describe('TicketNumbersView', () => {
  it('previews and saves the numbering', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = new FakeApi()
      .json('GET', PATH, SAVED)
      .json('PUT', PATH, { ...SAVED, prefix: 'Ticket#', start: 5000, next_number: 5000, next_tag: '[Ticket#5000]' })
    await mountView(TicketNumbersView, { path: `/t/${TENANT_ID}/ticketNumbers` })
    expect(preview()).toBe('[#1042]')

    await $('[data-test=prefix]').setValue('Ticket#')
    expect(preview()).toBe('[Ticket#1042]')
    await $('[data-test=start]').setValue('5000')
    expect(preview()).toBe('[Ticket#5000]')
    await click('[data-test=checksum]')
    expect(preview()).toBe('[Ticket#50005]')
    await click('[data-test=checksum]')
    await click('[data-test=numbers-save]')
    expect(fake.last('PUT', PATH)!.body).toEqual({
      format: 'increment',
      start: 5000,
      date_digits: 4,
      checksum: false,
      prefix: 'Ticket#',
    })
    expect(toasts.success()).toContain('The ticket numbers are saved.')

    await $('[data-test=format-date]').setValue(true)
    await $('[data-test=date-digits] select').setValue('3')
    expect(preview()).toMatch(/^\[Ticket#\d{8}001\]$/)
    await $('[data-test=prefix]').setValue(' ')
    expect(preview()).toMatch(/^\[#\d{11}\]$/)

    fake.on('PUT', PATH, {
      status: 422,
      body: { error: 'invalid_numbering', message: 'x', params: { field: 'start', minimum: 1043 } },
    })
    await click('[data-test=numbers-save]')
    expect(text()).toContain('The start has to lie above the last number: 1043 or more.')
  })

  it('shows a failure to load', async () => {
    inTenant()
    new FakeApi().error('GET', PATH, 403, 'forbidden', 'Not allowed')
    await mountView(TicketNumbersView, { path: `/t/${TENANT_ID}/ticketNumbers` })
    expect(text()).toContain('You are not allowed to do this.')
  })
})
