import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import AdminLayout from '@/app/AdminLayout.vue'
import LegalView from '@/app/LegalView.vue'
import NotFoundView from '@/app/NotFoundView.vue'
import PlainLayout from '@/app/PlainLayout.vue'
import { createAppRouter } from '@/app/router'
import { i18n } from '@/core/i18n/i18n'
import { useSession } from '@/modules/identity/session'
import { LAST_TENANT_KEY, rememberInvitation } from '@/modules/tenancy/tenants'
import { FakeApi } from '../support/fake-api'
import { ROLE_PERMISSIONS, tenant, TENANT_ID, user } from '../support/fixtures'
import { $, click, mountView, text } from '../support/mount'

async function boot(path: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const wrapper = mount(App, { global: { plugins: [router, i18n] }, attachTo: document.body })
  await flushPromises()
  return { router, wrapper }
}

describe('router', () => {
  it('sends visitors from the start page to the login', async () => {
    new FakeApi().json('GET', '/auth/session', { user: null })
    const { router, wrapper } = await boot('/')
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.text()).toContain('Welcome back to zendiloHUB')
    wrapper.unmount()
  })

  it('sends a new self-hosted instance to the setup wizard, and nowhere else', async () => {
    new FakeApi().json('GET', '/setup', { open: true, self_hosted: true }).json('GET', '/auth/session', { user: null })
    const { router, wrapper } = await boot('/login')
    expect(router.currentRoute.value.name).toBe('setup')
    expect(wrapper.text()).toContain('Set up zendiloHUB')
    wrapper.unmount()
  })

  it('keeps the setup wizard closed once the instance is set up', async () => {
    new FakeApi().json('GET', '/setup', { open: false, self_hosted: true }).json('GET', '/auth/session', { user: null })
    const { router, wrapper } = await boot('/setup')
    expect(router.currentRoute.value.name).toBe('login')
    wrapper.unmount()
  })

  it('sends users without an organization to the onboarding', async () => {
    new FakeApi().json('GET', '/auth/session', { user: user() }).json('GET', '/tenants', [])
    const { router, wrapper } = await boot('/')
    expect(router.currentRoute.value.name).toBe('onboarding')
    wrapper.unmount()
  })

  it('opens the organization the user worked in last', async () => {
    const other = tenant({ id: '00000000-0000-7000-8000-000000000002', name: 'Other AG' })
    localStorage.setItem(LAST_TENANT_KEY, other.id)
    new FakeApi()
      .json('GET', '/auth/session', { user: user() })
      .json('GET', '/tenants', [tenant(), other])
      .json('GET', /\/tenants\/.+\/members/, [])
    const { router, wrapper } = await boot('/')
    expect(router.currentRoute.value.fullPath).toBe(`/t/${other.id}/overview`)
    expect($('[data-test=tenant-name]').text()).toBe('Other AG')
    wrapper.unmount()
  })

  it('comes back to an invitation opened before the login', async () => {
    rememberInvitation('secret')
    new FakeApi().json('GET', '/auth/session', { user: user() }).json('POST', '/invitations/preview', {
      tenant_name: 'Acme GmbH',
      email: 'ada@example.org',
      role: 'agent',
      expires_at: '2026-10-29T12:00:00Z',
    })
    const { router, wrapper } = await boot('/')
    expect(router.currentRoute.value.fullPath).toBe('/invitations?token=secret')
    wrapper.unmount()
  })

  it('keeps users out of organizations they cannot use', async () => {
    new FakeApi()
      .json('GET', '/auth/session', { user: user() })
      .json('GET', '/tenants', [tenant({ status: 'suspended' })])
    const { router, wrapper } = await boot(`/t/${TENANT_ID}/overview`)
    expect(router.currentRoute.value.name).toBe('onboarding')
    wrapper.unmount()
  })

  it('sends roles without the permission of a page to the dashboard', async () => {
    new FakeApi()
      .json('GET', '/auth/session', { user: user() })
      .json('GET', '/tenants', [tenant({ role: 'agent' })])
      .json('GET', /\/tenants\/.+\/members/, [])
    const { router, wrapper } = await boot(`/t/${TENANT_ID}/settings`)
    expect(router.currentRoute.value.name).toBe('overview')
    await router.push(`/t/${TENANT_ID}`)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('overview')
    wrapper.unmount()
  })

  it('forgets the organizations of a user who logs out', async () => {
    new FakeApi().json('GET', '/auth/session', { user: user() }).json('GET', '/tenants', [tenant()])
    const { router, wrapper } = await boot('/onboarding')
    await router.push('/')
    await flushPromises()
    useSession().expire()
    await flushPromises()
    await router.push('/')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    wrapper.unmount()
  })

  it('resolves the view of every route', async () => {
    const router = createAppRouter(createMemoryHistory())
    const loaders = router
      .getRoutes()
      .map((route) => route.components?.default)
      .filter((component) => typeof component === 'function')
    expect(loaders.length).toBeGreaterThan(20)
    for (const load of loaders) {
      await expect((load as () => Promise<unknown>)()).resolves.toBeDefined()
    }
  })

  it('restores the scroll position when going back', () => {
    const router = createAppRouter(createMemoryHistory())
    const behavior = router.options.scrollBehavior
    const saved = { left: 0, top: 120 }
    expect(behavior?.(router.currentRoute.value, router.currentRoute.value, saved)).toEqual(saved)
    expect(behavior?.(router.currentRoute.value, router.currentRoute.value, null)).toEqual({ top: 0 })
  })
})

describe('PlainLayout', () => {
  it('switches the language', async () => {
    await mountView(PlainLayout)
    expect($('[data-test=brand]').text()).toContain('zendiloHUB')
    await click('[data-test=locale]')
    await click('[data-test=locale-de]')
    expect($('[data-test=locale]').text()).toContain('de')
    expect(document.documentElement.lang).toBe('de')
    expect(text()).toContain('Impressum')
    expect(text()).toContain(`© ${new Date().getFullYear()} zendiloHUB`)
  })

  it('switches between light and dark mode', async () => {
    await mountView(PlainLayout)
    const before = document.documentElement.classList.contains('dark')
    await click('[data-test=theme]')
    expect(document.documentElement.classList.contains('dark')).toBe(!before)
    await click('[data-test=theme]')
    expect(document.documentElement.classList.contains('dark')).toBe(before)
  })
})

describe('views', () => {
  it('shows placeholders for the legal pages', async () => {
    await mountView(LegalView, { props: { page: 'imprint' } })
    expect(text()).toContain('Imprint')
    expect(text()).toContain('This page is a placeholder')
  })

  it('explains a missing page', async () => {
    await mountView(NotFoundView)
    expect(text()).toContain('Page not found')
  })

  it('shows the tabs of the platform administration', async () => {
    await mountView(AdminLayout, { path: '/admin/tenants' })
    expect($('[data-test=admin-tabs]').text()).toContain('Organizations')
    expect($('[data-test=admin-tabs]').text()).toContain('Users')
  })
})

describe('The pages of an organization', () => {
  it('only ask for rights that exist, or nobody could open them', () => {
    const asked = createAppRouter(createMemoryHistory())
      .getRoutes()
      .map((route) => route.meta.permission)
      .filter((permission) => permission !== undefined)
    expect(asked.length).toBeGreaterThan(3)
    expect(asked.filter((permission) => !(ROLE_PERMISSIONS.owner as unknown[]).includes(permission))).toEqual([])
  })
})
