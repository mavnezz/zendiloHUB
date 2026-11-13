import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { http } from '@/core/api/http'
import { setLocale } from '@/core/i18n/i18n'
import { installGuard, safeRedirect } from '@/core/router/guard'
import UserMenu from '@/modules/identity/components/UserMenu.vue'
import { installLocaleSync, useSession } from '@/modules/identity/session'
import { FakeApi } from '../../support/fake-api'
import { user } from '../../support/fixtures'
import { click, exists, flushPromises, mountView, text } from '../../support/mount'

const Page = { render: () => null }

function guardedRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'start', component: Page },
      { path: '/login', name: 'login', component: Page, meta: { guestOnly: true } },
      { path: '/account', name: 'account', component: Page, meta: { requiresAuth: true } },
      { path: '/admin', name: 'admin', component: Page, meta: { requiresAdmin: true } },
    ],
  })
  installGuard(router, useSession())
  return router
}

describe('guard', () => {
  it('sends visitors to the login page and back', async () => {
    new FakeApi().json('GET', '/auth/session', { user: null })
    const router = guardedRouter()
    await router.push('/account')
    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/account')
    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('keeps users out of admin pages and away from the login page', async () => {
    new FakeApi().json('GET', '/auth/session', { user: user() })
    const router = guardedRouter()
    await router.push('/account')
    expect(router.currentRoute.value.name).toBe('account')
    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('start')
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('start')
  })

  it('lets administrators in', async () => {
    new FakeApi().json('GET', '/auth/session', { user: user({ role: 'admin' }) })
    const router = guardedRouter()
    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('admin')
  })

  it('copes with an unreachable server', async () => {
    new FakeApi().error('GET', '/auth/session', 502, 'http_error')
    const router = guardedRouter()
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('start')
  })

  it('goes to the login page when the session expires on a protected page', async () => {
    new FakeApi().json('GET', '/auth/session', { user: user() }).error('GET', '/account', 401, 'unauthenticated')
    const router = guardedRouter()
    await router.push('/account')
    await http.get('/account').catch(() => undefined)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/account')
    expect(useSession().authenticated.value).toBe(false)

    await router.push('/')
    await http.get('/account').catch(() => undefined)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('start')
  })

  it('only redirects within the app', () => {
    expect(safeRedirect('/account')).toBe('/account')
    expect(safeRedirect('//evil.example')).toBe('/')
    expect(safeRedirect('/\\evil.example')).toBe('/')
    expect(safeRedirect('https://evil.example')).toBe('/')
    expect(safeRedirect(undefined)).toBe('/')
  })
})

describe('session', () => {
  it('loads once unless forced', async () => {
    const api = new FakeApi().json('GET', '/auth/session', { user: user() })
    const session = useSession()
    await session.load()
    await session.load()
    expect(api.calls('GET', '/auth/session')).toHaveLength(1)
    await session.load(true)
    expect(api.calls('GET', '/auth/session')).toHaveLength(2)
    expect(session.loaded.value).toBe(true)
  })

  it('switches the account language along with the app language', async () => {
    const api = new FakeApi().on('PATCH', '/account', (request) => ({
      body: user({ locale: (request.body as { locale: 'de' | 'en' }).locale }),
    }))
    installLocaleSync()
    installLocaleSync()
    setLocale('de')
    await flushPromises()
    expect(api.calls('PATCH', '/account')).toHaveLength(0)

    useSession().start(user({ locale: 'de' }))
    setLocale('en')
    await flushPromises()
    expect(api.calls('PATCH', '/account')).toHaveLength(1)
    expect(useSession().user.value?.locale).toBe('en')

    api.error('PATCH', '/account', 500, 'internal_error')
    setLocale('de')
    await flushPromises()
    expect(useSession().user.value?.locale).toBe('en')
  })
})

describe('UserMenu', () => {
  it('offers login and sign-up to visitors', async () => {
    await mountView(UserMenu)
    expect(exists('[data-test=nav-login]')).toBe(true)
    expect(exists('[data-test=nav-register]')).toBe(true)
  })

  it('opens the account, the admin area and logs out', async () => {
    useSession().start(user({ role: 'admin' }))
    const api = new FakeApi().on('POST', '/auth/logout', { status: 204 })
    const { router } = await mountView(UserMenu)
    await click('[data-test=user-menu]')
    expect(text()).toContain('ada@example.org')
    await click('[data-test=menu-account]')
    expect(router.currentRoute.value.name).toBe('account')
    await click('[data-test=user-menu]')
    await click('[data-test=menu-admin]')
    expect(router.currentRoute.value.name).toBe('admin-tenants')
    await click('[data-test=user-menu]')
    await click('[data-test=menu-logout]')
    await flushPromises()
    expect(api.calls('POST', '/auth/logout')).toHaveLength(1)
    expect(useSession().authenticated.value).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('logs out locally even if the server fails', async () => {
    useSession().start(user())
    new FakeApi().error('POST', '/auth/logout', 500, 'internal_error')
    await mountView(UserMenu)
    await click('[data-test=user-menu]')
    expect(exists('[data-test=menu-admin]')).toBe(false)
    await click('[data-test=menu-logout]')
    await flushPromises()
    expect(useSession().authenticated.value).toBe(false)
  })
})
