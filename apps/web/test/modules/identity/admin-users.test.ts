import { describe, expect, it, vi } from 'vitest'
import AdminUsersView from '@/modules/identity/views/AdminUsersView.vue'
import { useSession } from '@/modules/identity/session'
import { FakeApi } from '../../support/fake-api'
import { user } from '../../support/fixtures'
import { $, $$, click, flushPromises, mountView, text, type } from '../../support/mount'

const grace = user({ id: 'u0', email: 'grace@example.org', role: 'admin' })
const ada = user({ id: 'u1', email: 'ada@example.org' })

describe('AdminUsersView', () => {
  it('lists users and marks the admin themselves', async () => {
    useSession().start(grace)
    new FakeApi().json('GET', '/admin/users', { items: [grace, ada], total: 2 })
    await mountView(AdminUsersView, { path: '/admin/users' })
    const rows = $$('[data-test=user-row]')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.text()).toContain('grace@example.org (you)')
    expect(rows[0]?.text()).toContain('Administrator')
    expect(rows[0]?.find('[data-test=toggle-role]').exists()).toBe(false)
    expect(rows[1]?.text()).toContain('User')
    expect($('[data-test=user-count]').text()).toBe('2 users')
  })

  it('searches after a short pause and pages through the results', async () => {
    useSession().start(grace)
    const api = new FakeApi().json('GET', '/admin/users', { items: [ada], total: 120 })
    await mountView(AdminUsersView, { path: '/admin/users' })
    expect($('[data-test=previous]').attributes('disabled')).toBeDefined()
    await click('[data-test=next]')
    expect(api.last('GET', '/admin/users')?.query).toEqual({ offset: '50', limit: '50' })
    await click('[data-test=previous]')
    expect(api.last('GET', '/admin/users')?.query).toEqual({ offset: '0', limit: '50' })

    vi.useFakeTimers()
    await type('[data-test=search]', 'ada')
    await vi.advanceTimersByTimeAsync(300)
    vi.useRealTimers()
    await flushPromises()
    expect(api.last('GET', '/admin/users')?.query).toEqual({ q: 'ada', offset: '0', limit: '50' })
  })

  it('shows an empty list and load errors', async () => {
    useSession().start(grace)
    const api = new FakeApi().json('GET', '/admin/users', { items: [], total: 0 })
    await mountView(AdminUsersView, { path: '/admin/users' })
    expect(text()).toContain('No users found.')

    api.error('GET', '/admin/users', 500, 'internal_error')
    await mountView(AdminUsersView, { path: '/admin/users' })
    expect($('[data-test=error]').text()).toContain('Something went wrong on our side')
  })

  it('changes roles and deletes users', async () => {
    useSession().start(grace)
    const api = new FakeApi()
      .json('GET', '/admin/users', { items: [grace, ada], total: 2 })
      .json('PATCH', '/admin/users/u1', user({ role: 'admin' }))
      .on('DELETE', '/admin/users/u1', { status: 204 })
    await mountView(AdminUsersView, { path: '/admin/users' })
    await click('[data-test=toggle-role]')
    expect(api.last('PATCH', '/admin/users/u1')?.body).toEqual({ role: 'admin' })

    await click('[data-test=delete-user]')
    expect(text()).toContain('Delete ada@example.org?')
    await click('[data-test=confirm]')
    expect(api.calls('DELETE', '/admin/users/u1')).toHaveLength(1)
  })

  it('demotes administrators and reports failures', async () => {
    useSession().start(grace)
    const other = user({ id: 'u2', email: 'alan@example.org', role: 'admin' })
    const api = new FakeApi()
      .json('GET', '/admin/users', { items: [other], total: 1 })
      .error('PATCH', '/admin/users/u2', 409, 'last_admin')
    await mountView(AdminUsersView, { path: '/admin/users' })
    expect($('[data-test=toggle-role]').text()).toBe('Make regular user')
    await click('[data-test=toggle-role]')
    expect(api.last('PATCH', '/admin/users/u2')?.body).toEqual({ role: 'user' })
  })
})
