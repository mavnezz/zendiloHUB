import { describe, expect, it } from 'vitest'
import CompaniesView from '@/modules/customers/views/CompaniesView.vue'
import CompanyView from '@/modules/customers/views/CompanyView.vue'
import ContactsView from '@/modules/customers/views/ContactsView.vue'
import ContactView from '@/modules/customers/views/ContactView.vue'
import { useSession } from '@/modules/identity/session'
import type { Permission, TenantRole } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID, user } from '../../support/fixtures'
import { company, contact, queue, ticket } from '../../support/helpdesk'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const BASE = `/tenants/${TENANT_ID}`

function inTenant(role: TenantRole = 'owner', permissions?: Permission[]): void {
  useSession().start(user())
  useTenants().put(tenant({ role, ...(permissions ? { permissions } : {}) }))
  useTenants().select(TENANT_ID)
}

async function submitSearch(): Promise<void> {
  $('[data-test=search]').element.closest('form')!.dispatchEvent(new Event('submit'))
  await flushPromises()
}

describe('ContactsView', () => {
  it('lists, searches and creates contacts', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/contacts`, {
        items: [contact(), contact({ id: 'c2', name: 'Dora', company: null })],
        total: 2,
      })
      .json('GET', `${BASE}/companies`, { items: [company()], total: 1 })
      .json('POST', `${BASE}/contacts`, contact({ id: 'c3', name: 'Eve' }), 201)
    const { router } = await mountView(ContactsView, { path: `/t/${TENANT_ID}/contacts` })
    expect($$('[data-test=contact]')).toHaveLength(2)
    expect(text()).toContain('Acme')
    expect($('[data-test=count]').text()).toBe('2 contacts')

    await type('[data-test=search]', 'carl')
    await submitSearch()
    expect(fake.last('GET', `${BASE}/contacts`)?.query).toMatchObject({ q: 'carl', offset: '0' })

    await click('[data-test=create-contact]')
    await type('#contact-name', 'Eve')
    await type('#contact-email', 'eve@acme.example')
    await $('#contact-company').setValue('co1')
    await click('[data-test=save-contact]')
    expect(fake.last('POST', `${BASE}/contacts`)?.body).toEqual({
      name: 'Eve',
      email: 'eve@acme.example',
      phone: null,
      company_id: 'co1',
      notes: '',
    })
    expect(toasts.success()).toContain('Contact "Eve" created.')
    expect(router.currentRoute.value.params.contactId).toBe('c3')
  })

  it('shows an empty list, failures and no controls without the permission', async () => {
    inTenant('agent', ['customers.view'])
    new FakeApi().json('GET', `${BASE}/contacts`, { items: [], total: 0 })
    await mountView(ContactsView, { path: `/t/${TENANT_ID}/contacts` })
    expect(text()).toContain('No contacts yet')
    expect(exists('[data-test=create-contact]')).toBe(false)

    new FakeApi().error('GET', `${BASE}/contacts`, 500, 'internal_error')
    await mountView(ContactsView, { path: `/t/${TENANT_ID}/contacts` })
    expect(exists('[data-test=error]')).toBe(true)
  })
})

describe('ContactView', () => {
  function api(): FakeApi {
    return new FakeApi()
      .json('GET', `${BASE}/contacts/c1`, contact())
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [])
      .json('GET', `${BASE}/tickets`, { items: [ticket()], total: 1 })
      .json('GET', `${BASE}/companies`, { items: [company()], total: 1 })
  }

  it('shows the contact with their tickets, edits and deletes', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api()
      .json('PATCH', `${BASE}/contacts/c1`, contact({ name: 'Carl C.' }))
      .on('DELETE', `${BASE}/contacts/c1`, { status: 204 })
    const { router } = await mountView(ContactView, { path: `/t/${TENANT_ID}/contacts/c1` })
    expect($('[data-test=contact-name]').text()).toBe('Carl Customer')
    expect(text()).toContain('Prefers calls')
    expect(text()).toContain('Tickets (1)')
    expect(fake.last('GET', `${BASE}/tickets`)?.query).toMatchObject({ view: 'all', customer_id: 'c1' })

    await click('[data-test=edit-contact]')
    expect(($('#contact-email').element as HTMLInputElement).value).toBe('carl@acme.example')
    await type('#contact-name', 'Carl C.')
    await type('#contact-phone', '')
    await click('[data-test=save-contact]')
    expect(fake.last('PATCH', `${BASE}/contacts/c1`)?.body).toMatchObject({ name: 'Carl C.', phone: null })
    expect(toasts.success()).toContain('Contact "Carl C." saved.')

    await click('[data-test=delete-contact]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/contacts/c1`)).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('contacts')
  })

  it('reports what the server refuses', async () => {
    inTenant()
    api()
      .json('GET', `${BASE}/tickets`, { items: [], total: 0 })
      .error('PATCH', `${BASE}/contacts/c1`, 409, 'contact_email_taken')
    await mountView(ContactView, { path: `/t/${TENANT_ID}/contacts/c1` })
    expect(text()).toContain('No tickets yet.')
    await click('[data-test=edit-contact]')
    await click('[data-test=save-contact]')
    expect($('[role=dialog] [data-test=error]').text()).toContain(
      'There is already a contact with this e-mail address.',
    )

    new FakeApi().error('GET', `${BASE}/contacts/c1`, 404, 'contact_not_found')
    await mountView(ContactView, { path: `/t/${TENANT_ID}/contacts/c1` })
    expect(text()).toContain('The contact does not exist.')
  })
})

describe('CompaniesView and CompanyView', () => {
  it('lists, searches and creates companies', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/companies`, { items: [company()], total: 1 })
      .json('POST', `${BASE}/companies`, company({ id: 'co2', name: 'Beta' }), 201)
    const { router } = await mountView(CompaniesView, { path: `/t/${TENANT_ID}/companies` })
    expect($('[data-test=company]').text()).toContain('acme.example')
    await type('[data-test=search]', 'acme')
    await submitSearch()
    expect(fake.last('GET', `${BASE}/companies`)?.query.q).toBe('acme')

    await click('[data-test=create-company]')
    await type('#company-name', 'Beta')
    await type('#company-domain', 'beta.example')
    await click('[data-test=save-company]')
    expect(fake.last('POST', `${BASE}/companies`)?.body).toEqual({ name: 'Beta', domain: 'beta.example', notes: '' })
    expect(toasts.success()).toContain('Company "Beta" created.')
    expect(router.currentRoute.value.params.companyId).toBe('co2')

    new FakeApi().json('GET', `${BASE}/companies`, { items: [], total: 0 })
    await mountView(CompaniesView, { path: `/t/${TENANT_ID}/companies` })
    expect(text()).toContain('No companies yet')
    new FakeApi().error('GET', `${BASE}/companies`, 500, 'internal_error')
    await mountView(CompaniesView, { path: `/t/${TENANT_ID}/companies` })
    expect(exists('[data-test=error]')).toBe(true)
  })

  it('shows a company with its contacts and tickets, edits and deletes it', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = new FakeApi()
      .json('GET', `${BASE}/companies/co1`, company({ notes: 'Key account' }))
      .json('GET', `${BASE}/contacts`, { items: [contact()], total: 1 })
      .json('GET', `${BASE}/queues`, [queue()])
      .json('GET', `${BASE}/members`, [])
      .json('GET', `${BASE}/tickets`, { items: [ticket()], total: 1 })
      .json('PATCH', `${BASE}/companies/co1`, company({ name: 'Acme AG' }))
      .on('DELETE', `${BASE}/companies/co1`, { status: 204 })
    const { router } = await mountView(CompanyView, { path: `/t/${TENANT_ID}/companies/co1` })
    expect($('[data-test=company-name]').text()).toBe('Acme')
    expect($('[data-test=company-contacts]').text()).toContain('Carl Customer')
    expect(fake.last('GET', `${BASE}/tickets`)?.query).toMatchObject({ company_id: 'co1' })
    expect(text()).toContain('Key account')

    await click('[data-test=edit-company]')
    await type('#company-name', 'Acme AG')
    await type('#company-domain', '')
    await click('[data-test=save-company]')
    expect(fake.last('PATCH', `${BASE}/companies/co1`)?.body).toEqual({
      name: 'Acme AG',
      domain: null,
      notes: 'Key account',
    })
    expect(toasts.success()).toContain('Company "Acme AG" saved.')

    await click('[data-test=delete-company]')
    expect(text()).toContain('Its contacts stay')
    await click('[data-test=confirm]')
    expect(router.currentRoute.value.name).toBe('companies')
  })

  it('reports a refused change of a company', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/companies/co1`, company())
      .json('GET', `${BASE}/contacts`, { items: [], total: 0 })
      .json('GET', `${BASE}/queues`, [])
      .json('GET', `${BASE}/members`, [])
      .json('GET', `${BASE}/tickets`, { items: [], total: 0 })
      .error('PATCH', `${BASE}/companies/co1`, 409, 'company_domain_taken')
    await mountView(CompanyView, { path: `/t/${TENANT_ID}/companies/co1` })
    expect(text()).toContain('No tickets yet.')
    await click('[data-test=edit-company]')
    await click('[data-test=save-company]')
    expect(text()).toContain('Another company has this domain already.')
  })
})
