import { describe, expect, it } from 'vitest'
import { useInstance } from '@/core/instance'
import { useSession } from '@/modules/identity/session'
import LoginView from '@/modules/identity/views/LoginView.vue'
import SetupView from '@/modules/identity/views/SetupView.vue'
import OnboardingView from '@/modules/tenancy/views/OnboardingView.vue'
import { FakeApi } from '../../support/fake-api'
import { user } from '../../support/fixtures'
import { $, click, exists, mountView, type } from '../../support/mount'

const SELF_HOSTED = { open: false, self_hosted: true }

describe('SetupView', () => {
  it('sets up the instance and logs the administrator in', async () => {
    const api = new FakeApi()
      .json('GET', '/setup', { open: true, self_hosted: true })
      .json('POST', '/setup', { user: user({ role: 'admin', locale: 'de' }) })
    await useInstance().load()
    const { router } = await mountView(SetupView, { path: '/setup' })
    expect($('[data-test=submit]').attributes('disabled')).toBeDefined()

    await type('#token', ' 1a2b3c-4d5e6f-7a8b9c ')
    await type('#organization', 'Acme GmbH')
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')

    expect(api.last('POST', '/setup')?.body).toMatchObject({
      token: '1a2b3c-4d5e6f-7a8b9c',
      organization_name: 'Acme GmbH',
      email: 'ada@example.org',
      password: 'correct horse battery',
      locale: 'en',
    })
    expect(useSession().user.value?.role).toBe('admin')
    expect(useInstance().setupOpen.value).toBe(false)
    expect(router.currentRoute.value.name).toBe('start')
  })

  it('explains a wrong setup code', async () => {
    new FakeApi().error('POST', '/setup', 403, 'invalid_setup_token')
    await mountView(SetupView, { path: '/setup' })
    await type('#token', 'wrong')
    await type('#organization', 'Acme GmbH')
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    expect($('[data-test=error]').text()).toContain('The setup code is wrong. It is in the log of the server.')
  })
})

describe('A self-hosted instance', () => {
  it('has no sign-up link on the login page', async () => {
    new FakeApi().json('GET', '/setup', SELF_HOSTED)
    await useInstance().load()
    await mountView(LoginView, { path: '/login' })
    expect(exists('[data-test=sign-up]')).toBe(false)
  })

  it('offers the sign-up on SaaS', async () => {
    new FakeApi().json('GET', '/setup', { open: false, self_hosted: false })
    await useInstance().load()
    await mountView(LoginView, { path: '/login' })
    expect(exists('[data-test=sign-up]')).toBe(true)
  })

  it('sends people without an organization to their administrator', async () => {
    new FakeApi().json('GET', '/setup', SELF_HOSTED)
    await useInstance().load()
    useSession().start(user())
    await mountView(OnboardingView, { path: '/onboarding' })
    expect(exists('[data-test=wait-for-invitation]')).toBe(true)
    expect(exists('[data-test=submit]')).toBe(false)
  })
})
