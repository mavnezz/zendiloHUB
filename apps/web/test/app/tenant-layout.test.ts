import { describe, expect, it } from 'vitest'
import OverviewView from '@/app/OverviewView.vue'
import TenantLayout from '@/app/TenantLayout.vue'
import { useSession } from '@/modules/identity/session'
import type { TenantRole } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../support/fake-api'
import { member, tenant, TENANT_ID, user } from '../support/fixtures'
import { $, $$, click, exists, mountView, text } from '../support/mount'

const OTHER = '00000000-0000-7000-8000-000000000002'

function inTenant(role: TenantRole = 'owner'): void {
  useSession().start(user({ role: 'admin' }))
  const tenants = useTenants()
  tenants.put(tenant({ role }))
  tenants.put(tenant({ id: OTHER, name: 'Beta AG', role: 'agent' }))
  tenants.put(tenant({ id: '00000000-0000-7000-8000-000000000003', name: 'Gamma KG', status: 'suspended' }))
  tenants.select(TENANT_ID)
}

describe('TenantLayout', () => {
  it('shows the sidebar with everything the role may see', async () => {
    inTenant()
    await mountView(TenantLayout, { path: `/t/${TENANT_ID}/team` })
    expect($$('[data-test^=nav-group-]').map((group) => group.attributes('data-test'))).toEqual([
      'nav-group-workspace',
      'nav-group-organization',
    ])
    expect($('[data-test=nav-apiKeys]').attributes('href')).toBe(`/t/${TENANT_ID}/api-keys`)
    expect($('[data-test=nav-team]').attributes('data-active')).toBe('true')
    expect($('[data-test=breadcrumb-page]').text()).toBe('Team')
    expect($('[data-test=tenant-name]').text()).toBe('Acme GmbH')
  })

  it('hides what agents may not see', async () => {
    inTenant('agent')
    await mountView(TenantLayout, { path: `/t/${TENANT_ID}/team` })
    expect(exists('[data-test=nav-team]')).toBe(true)
    expect(exists('[data-test=nav-roles]')).toBe(true)
    expect(exists('[data-test=nav-settings]')).toBe(false)
    expect(exists('[data-test=nav-apiKeys]')).toBe(false)
    expect(exists('[data-test=nav-audit]')).toBe(false)
  })

  it('switches organizations and creates new ones', async () => {
    inTenant()
    const { router } = await mountView(TenantLayout, { path: `/t/${TENANT_ID}/overview` })
    await click('[data-test=tenant-switcher]')
    expect(text()).toContain('Gamma KG')
    expect(text()).toContain('(suspended)')
    await click(`[data-test=tenant-${OTHER}]`)
    expect(router.currentRoute.value.fullPath).toBe(`/t/${OTHER}/overview`)
    await click('[data-test=tenant-switcher]')
    await click('[data-test=tenant-create]')
    expect(router.currentRoute.value.name).toBe('onboarding')
  })

  it('opens the account and the administration and logs out', async () => {
    inTenant()
    const api = new FakeApi().on('POST', '/auth/logout', { status: 204 })
    const { router } = await mountView(TenantLayout, { path: `/t/${TENANT_ID}/overview` })
    await click('[data-test=user-menu]')
    await click('[data-test=menu-account]')
    expect(router.currentRoute.value.name).toBe('account')
    await router.push(`/t/${TENANT_ID}/overview`)
    await click('[data-test=user-menu]')
    await click('[data-test=menu-admin]')
    expect(router.currentRoute.value.name).toBe('admin-tenants')
    await router.push(`/t/${TENANT_ID}/overview`)
    await click('[data-test=user-menu]')
    await click('[data-test=menu-logout]')
    expect(api.calls('POST', '/auth/logout')).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('logs out locally even if the server fails', async () => {
    inTenant()
    new FakeApi().error('POST', '/auth/logout', 500, 'internal_error')
    const { router } = await mountView(TenantLayout, { path: `/t/${TENANT_ID}/overview` })
    await click('[data-test=user-menu]')
    await click('[data-test=menu-logout]')
    expect(useSession().authenticated.value).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
  })
})

describe('OverviewView', () => {
  it('guides through the first steps and remembers when they were hidden', async () => {
    inTenant()
    new FakeApi().json('GET', `/tenants/${TENANT_ID}/members`, [member(), member({ user_id: 'u2' })])
    await mountView(OverviewView, { path: `/t/${TENANT_ID}/overview` })
    // The team has a second member already.
    expect($('[data-test=setup-progress]').text()).toBe('1 of 2 steps done')
    expect($('[data-test=step-settings]').attributes('href')).toBe(`/t/${TENANT_ID}/settings`)
    expect($('[data-test=step-team]').classes()).toContain('bg-primary/5')

    await click('[data-test=setup-dismiss]')
    expect(exists('[data-test=setup]')).toBe(false)
    expect(localStorage.getItem(`zendilohub.setup-dismissed.${TENANT_ID}`)).toBe('1')
  })

  it('shows agents the steps they cannot take as plain text', async () => {
    inTenant('agent')
    new FakeApi().json('GET', `/tenants/${TENANT_ID}/members`, [member()])
    await mountView(OverviewView, { path: `/t/${TENANT_ID}/overview` })
    expect($('[data-test=step-settings]').element.tagName).toBe('DIV')
    expect($('[data-test=step-team]').attributes('href')).toBe(`/t/${TENANT_ID}/team`)
  })

  it('stays hidden once dismissed and copes without the member list', async () => {
    inTenant()
    localStorage.setItem(`zendilohub.setup-dismissed.${TENANT_ID}`, '1')
    new FakeApi().error('GET', `/tenants/${TENANT_ID}/members`, 500, 'internal_error')
    await mountView(OverviewView, { path: `/t/${TENANT_ID}/overview` })
    expect(exists('[data-test=setup]')).toBe(false)
    localStorage.clear()
    await mountView(OverviewView, { path: `/t/${TENANT_ID}/overview` })
    expect($('[data-test=setup-progress]').text()).toBe('0 of 2 steps done')
  })
})
