import { describe, expect, it } from 'vitest'
import type { AuditEntry } from '@/modules/compliance/api'
import AdminAuditLogView from '@/modules/compliance/views/AdminAuditLogView.vue'
import AuditLogView from '@/modules/compliance/views/AuditLogView.vue'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID } from '../../support/fixtures'
import { $, $$, click, exists, mountView, text } from '../../support/mount'

function entry(overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: 'a1',
    tenant_id: TENANT_ID,
    actor_email: 'ada@example.org',
    action: 'member.role_changed',
    target: 'bob@example.org: manager',
    succeeded: true,
    status: 200,
    client: '203.0.113.7',
    created_at: '2026-10-28T12:00:00Z',
    ...overrides,
  }
}

function inTenant(): void {
  useTenants().put(tenant())
  useTenants().select(TENANT_ID)
}

describe('AuditLogView', () => {
  it('shows who changed what, in words', async () => {
    inTenant()
    new FakeApi().json('GET', `/tenants/${TENANT_ID}/audit-log`, {
      items: [
        entry(),
        entry({ id: 'a2', action: 'tenant.updated', succeeded: false, status: 403, actor_email: null, target: null }),
        entry({ id: 'a3', action: 'calls.something_new' }),
      ],
      total: 3,
    })
    await mountView(AuditLogView, { path: `/t/${TENANT_ID}/audit` })
    const actions = $$('[data-test=action]').map((cell) => cell.text())
    expect(actions).toEqual(['Changed a role', 'Changed the settings', 'calls.something_new'])
    expect(text()).toContain('bob@example.org: manager')
    expect(text()).toContain('Deleted or unknown account')
    expect($('[data-test=failed]').text()).toContain('Failed (403)')
    expect($('[data-test=count]').text()).toBe('3 entries')
  })

  it('pages through long logs', async () => {
    inTenant()
    const api = new FakeApi().json('GET', `/tenants/${TENANT_ID}/audit-log`, { items: [entry()], total: 120 })
    await mountView(AuditLogView, { path: `/t/${TENANT_ID}/audit` })
    expect($('[data-test=previous]').attributes('disabled')).toBeDefined()
    await click('[data-test=next]')
    expect(api.last('GET', `/tenants/${TENANT_ID}/audit-log`)?.query).toEqual({ offset: '50', limit: '50' })
    await click('[data-test=previous]')
    expect(api.last('GET', `/tenants/${TENANT_ID}/audit-log`)?.query.offset).toBe('0')
  })

  it('reports failures', async () => {
    inTenant()
    new FakeApi().error('GET', `/tenants/${TENANT_ID}/audit-log`, 403, 'permission_denied')
    await mountView(AuditLogView, { path: `/t/${TENANT_ID}/audit` })
    expect($('[data-test=error]').text()).toContain('Your role does not allow this.')
  })
})

describe('AdminAuditLogView', () => {
  it('shows the whole platform', async () => {
    new FakeApi().json('GET', '/admin/audit-log', {
      items: [entry({ action: 'auth.login', tenant_id: null })],
      total: 1,
    })
    await mountView(AdminAuditLogView, { path: '/admin/audit-log' })
    expect($('[data-test=action]').text()).toBe('Logged in')
    expect(text()).toContain('Every change on the platform')
  })

  it('says when there is nothing yet, and reports failures', async () => {
    new FakeApi().json('GET', '/admin/audit-log', { items: [], total: 0 })
    await mountView(AdminAuditLogView, { path: '/admin/audit-log' })
    expect(text()).toContain('No entries yet.')
    new FakeApi().error('GET', '/admin/audit-log', 500, 'internal_error')
    await mountView(AdminAuditLogView, { path: '/admin/audit-log' })
    expect(exists('[data-test=error]')).toBe(true)
  })
})
