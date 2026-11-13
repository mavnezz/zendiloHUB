import { describe, expect, it } from 'vitest'
import { LAST_TENANT_KEY, rememberInvitation, takePendingInvitation, useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID } from '../../support/fixtures'

const OTHER = '00000000-0000-7000-8000-000000000002'

describe('useTenants', () => {
  it('loads the organizations once', async () => {
    const api = new FakeApi().json('GET', '/tenants', [tenant()])
    const tenants = useTenants()
    await tenants.load()
    await tenants.load()
    expect(api.calls('GET', '/tenants')).toHaveLength(1)
    expect(tenants.loaded.value).toBe(true)
    await tenants.load(true)
    expect(api.calls('GET', '/tenants')).toHaveLength(2)
  })

  it('prefers the organization used last, else the first active one', () => {
    const tenants = useTenants()
    expect(tenants.preferred()).toBeNull()
    tenants.put(tenant({ id: OTHER, name: 'Beta', status: 'suspended' }))
    tenants.put(tenant({ name: 'Alpha' }))
    expect(tenants.preferred()?.id).toBe(TENANT_ID)
    localStorage.setItem(LAST_TENANT_KEY, OTHER)
    // Suspended: not usable.
    expect(tenants.preferred()?.id).toBe(TENANT_ID)
    expect(tenants.usable(OTHER)).toBe(false)
    expect(tenants.usable(TENANT_ID)).toBe(true)
  })

  it('selects, replaces and forgets organizations', () => {
    const tenants = useTenants()
    tenants.put(tenant({ name: 'Zeta' }))
    tenants.put(tenant({ id: OTHER, name: 'Alpha' }))
    expect(tenants.tenants.value.map((each) => each.name)).toEqual(['Alpha', 'Zeta'])

    tenants.select(TENANT_ID)
    expect(tenants.current.value?.name).toBe('Zeta')
    expect(localStorage.getItem(LAST_TENANT_KEY)).toBe(TENANT_ID)
    tenants.put(tenant({ name: 'Zeta AG' }))
    expect(tenants.current.value?.name).toBe('Zeta AG')

    tenants.forget(OTHER)
    expect(tenants.current.value?.name).toBe('Zeta AG')
    tenants.forget(TENANT_ID)
    expect(tenants.current.value).toBeNull()
    expect(tenants.tenants.value).toEqual([])
  })

  it('answers what the role in the current organization allows', () => {
    const tenants = useTenants()
    expect(tenants.can('members.view')).toBe(false)
    tenants.put(tenant({ role: 'agent' }))
    tenants.select(TENANT_ID)
    expect(tenants.can('members.view')).toBe(true)
    expect(tenants.can('members.manage')).toBe(false)
  })

  it('remembers an invitation for after the login, once', () => {
    expect(takePendingInvitation()).toBeNull()
    rememberInvitation('secret')
    expect(takePendingInvitation()).toBe('secret')
    expect(takePendingInvitation()).toBeNull()
  })
})
