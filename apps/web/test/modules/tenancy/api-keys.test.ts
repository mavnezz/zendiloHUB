import { describe, expect, it } from 'vitest'
import { API_KEY_PERMISSIONS, READ_PERMISSIONS, type ApiKey } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import ApiKeysView from '@/modules/tenancy/views/ApiKeysView.vue'
import { FakeApi } from '../../support/fake-api'
import { tenant, TENANT_ID } from '../../support/fixtures'
import { $, $$, click, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const PATH = `/t/${TENANT_ID}/api-keys`
const KEYS = `/tenants/${TENANT_ID}/api-keys`

function inTenant(): void {
  const tenants = useTenants()
  tenants.put(tenant())
  tenants.select(TENANT_ID)
}

function key(overrides: Partial<ApiKey> = {}): ApiKey {
  return {
    id: 'k1',
    name: 'Directory sync',
    permissions: ['members.view'],
    start: 'zhk_Ab3dE7f',
    created_at: '2026-11-13T12:00:00Z',
    last_used_at: null,
    ...overrides,
  }
}

function checked(permission: string): boolean {
  return $(`[data-test="permission-${permission}"]`).attributes('data-state') === 'checked'
}

describe('ApiKeysView', () => {
  it('creates a key with the permissions it needs and shows it once', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = new FakeApi()
      .json('GET', KEYS, [
        key({ last_used_at: '2026-11-13T13:00:00Z' }),
        key({ id: 'k2', permissions: [...API_KEY_PERMISSIONS] }),
      ])
      .json('POST', KEYS, { api_key: key({ id: 'k3', name: 'Reports' }), key: 'zhk_full-key' }, 201)
    await mountView(ApiKeysView, { path: PATH })

    const [listed] = $$('[data-test=api-key]')
    expect(listed!.text()).toContain('Directory sync')
    expect(listed!.text()).toContain('zhk_Ab3dE7f…')
    expect(listed!.find('[data-test=api-key-used]').text()).toContain('Last used')
    expect($$('[data-test=api-key-scope]').map((each) => each.text())).toEqual(['1 permission', 'All permissions'])
    expect($('[data-test=example-members]').text()).toContain(`/api/v1/tenants/${TENANT_ID}/members`)
    expect($('[data-test=example-auditLog]').text()).toContain('Bearer zhk_')
    expect($('[data-test=reference]').attributes('href')).toBe('/api/reference')

    await click('[data-test=create-key]')
    for (const permission of READ_PERMISSIONS) {
      expect(checked(permission)).toBe(true)
    }
    await click('[data-test=preset-none]')
    expect($('[data-test=save-key]').attributes('disabled')).toBeDefined()
    await click('[data-test="permission-audit.view"]')
    await type('#api-key-name', ' Reports ')
    await click('[data-test=save-key]')
    expect(fake.last('POST', KEYS)?.body).toEqual({ name: 'Reports', permissions: ['audit.view'] })
    expect(toasts.success()).toContain('API key "Reports" created')
    expect($('[data-test=secret]').text()).toBe('zhk_full-key')
    expect(text()).toContain('Your API key')
  })

  it('changes and deletes a key', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = new FakeApi()
      .json('GET', KEYS, [key()])
      .json('PATCH', `${KEYS}/k1`, key({ name: 'Audit export', permissions: ['audit.view'] }))
      .on('DELETE', `${KEYS}/k1`, { status: 204 })
    await mountView(ApiKeysView, { path: PATH })
    expect($('[data-test=api-key-used]').text()).toBe('Not used yet')

    await click('[data-test=edit-key-k1]')
    expect(text()).toContain('Edit key')
    await click('[data-test="permission-members.view"]')
    await click('[data-test="permission-audit.view"]')
    await type('#api-key-name', 'Audit export')
    await click('[data-test=save-key]')
    expect(fake.last('PATCH', `${KEYS}/k1`)?.body).toEqual({ name: 'Audit export', permissions: ['audit.view'] })
    expect(toasts.success()).toContain('API key "Audit export" saved')

    await click('[data-test=remove-key-k1]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${KEYS}/k1`)).toHaveLength(1)
  })

  it('reports a failing list of keys', async () => {
    inTenant()
    new FakeApi().error('GET', KEYS, 500, 'internal_error')
    await mountView(ApiKeysView, { path: PATH })
    expect($$('[data-test=error]')).toHaveLength(1)
  })
})
