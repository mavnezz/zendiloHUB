import { describe, expect, it } from 'vitest'
import ForgotPasswordView from '@/modules/identity/views/ForgotPasswordView.vue'
import LoginView from '@/modules/identity/views/LoginView.vue'
import RegisterView from '@/modules/identity/views/RegisterView.vue'
import ResetPasswordView from '@/modules/identity/views/ResetPasswordView.vue'
import VerifyEmailView from '@/modules/identity/views/VerifyEmailView.vue'
import { useSession } from '@/modules/identity/session'
import { setLocale } from '@/core/i18n/i18n'
import { FakeApi } from '../../support/fake-api'
import { user } from '../../support/fixtures'
import { $, click, exists, flushPromises, mountView, text, type } from '../../support/mount'

describe('LoginView', () => {
  it('logs in and goes where the user wanted to go', async () => {
    const api = new FakeApi().json('POST', '/auth/login', { user: user({ locale: 'de' }) })
    const { router } = await mountView(LoginView, { path: '/login?redirect=/account' })
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    expect(api.last('POST', '/auth/login')?.body).toEqual({
      email: 'ada@example.org',
      password: 'correct horse battery',
    })
    expect(router.currentRoute.value.fullPath).toBe('/account')
    expect(useSession().user.value?.email).toBe('ada@example.org')
    // The app now speaks the account's language.
    expect(document.documentElement.lang).toBe('de')
  })

  it('shows why a login failed', async () => {
    new FakeApi().error('POST', '/auth/login', 401, 'invalid_credentials')
    await mountView(LoginView, { path: '/login' })
    await type('#email', 'ada@example.org')
    await type('#password', 'wrong')
    await click('[data-test=submit]')
    expect($('[data-test=error]').text()).toContain('E-mail address or password is wrong.')
  })

  it('offers a new confirmation link for an unconfirmed sign-up', async () => {
    const api = new FakeApi()
      .error('POST', '/auth/login', 403, 'email_not_verified')
      .on('POST', '/auth/resend-confirmation', { status: 204 })
    await mountView(LoginView, { path: '/login' })
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    expect(exists('[data-test=error]')).toBe(false)
    expect($('[data-test=notice]').text()).toContain('Please confirm your e-mail address first')
    await click('[data-test=resend]')
    expect(api.last('POST', '/auth/resend-confirmation')?.body).toEqual({
      email: 'ada@example.org',
      password: 'correct horse battery',
    })
    expect($('[data-test=resent]').text()).toContain('a new link is on its way')
  })

  it('reports a failed resend', async () => {
    new FakeApi()
      .error('POST', '/auth/login', 403, 'email_not_verified')
      .error('POST', '/auth/resend-confirmation', 429, 'too_many_requests')
    await mountView(LoginView, { path: '/login' })
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    await click('[data-test=resend]')
    expect(exists('[data-test=resent]')).toBe(false)
  })
})

describe('RegisterView', () => {
  it('signs up in the current language and asks to check the inbox', async () => {
    setLocale('de')
    const api = new FakeApi().on('POST', '/auth/register', { status: 204 })
    await mountView(RegisterView, { path: '/register' })
    expect(text()).toContain('Mit der Registrierung akzeptierst du die AGB und die Datenschutz.')
    await type('#email', ' ada@example.org ')
    await type('#password', 'short')
    expect($('[data-test=submit]').attributes('disabled')).toBeDefined()
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    // E-mail inputs drop surrounding blanks.
    expect(api.last('POST', '/auth/register')?.body).toEqual({
      email: 'ada@example.org',
      password: 'correct horse battery',
      locale: 'de',
    })
    expect($('[data-test=notice]').text()).toContain('an ada@example.org geschickt')
  })

  it('shows validation errors', async () => {
    new FakeApi().on('POST', '/auth/register', {
      status: 422,
      body: { error: 'weak_password', message: 'weak', params: { min_length: 10, max_length: 128 } },
    })
    await mountView(RegisterView, { path: '/register' })
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    expect($('[data-test=error]').text()).toContain('between 10 and 128 characters')
  })
})

describe('VerifyEmailView', () => {
  it('confirms the sign-up, logs in and goes to the start page', async () => {
    const api = new FakeApi().json('POST', '/auth/confirm', { user: user() })
    const { router } = await mountView(VerifyEmailView, { path: '/verify-email?token=abc' })
    await flushPromises()
    expect(api.last('POST', '/auth/confirm')?.body).toEqual({ token: 'abc' })
    expect(useSession().authenticated.value).toBe(true)
    expect(router.currentRoute.value.name).toBe('start')
  })

  it('explains a link that does not work', async () => {
    new FakeApi().error('POST', '/auth/confirm', 422, 'invalid_token')
    await mountView(VerifyEmailView, { path: '/verify-email?token=used' })
    await flushPromises()
    expect(text()).toContain('This link does not work')
    expect(text()).toContain('If your account exists, just log in.')
  })

  it('explains an incomplete link', async () => {
    await mountView(VerifyEmailView, { path: '/verify-email' })
    expect(text()).toContain('The link is incomplete')
  })
})

describe('ForgotPasswordView', () => {
  it('sends a reset link', async () => {
    const api = new FakeApi().on('POST', '/auth/forgot-password', { status: 204 })
    await mountView(ForgotPasswordView, { path: '/forgot-password' })
    await type('#email', 'ada@example.org')
    await click('[data-test=submit]')
    expect(api.last('POST', '/auth/forgot-password')?.body).toEqual({ email: 'ada@example.org' })
    expect($('[data-test=notice]').text()).toContain('If there is an account for ada@example.org')
  })

  it('shows errors', async () => {
    new FakeApi().error('POST', '/auth/forgot-password', 429, 'too_many_requests')
    await mountView(ForgotPasswordView, { path: '/forgot-password' })
    await type('#email', 'ada@example.org')
    await click('[data-test=submit]')
    expect($('[data-test=error]').text()).toContain('Too many attempts')
  })
})

describe('ResetPasswordView', () => {
  it('sets the new password, logs in and opens the account', async () => {
    const api = new FakeApi().json('POST', '/auth/reset-password', { user: user() })
    const { router } = await mountView(ResetPasswordView, { path: '/reset-password?token=abc' })
    await type('#password', 'a new password')
    await click('[data-test=submit]')
    expect(api.last('POST', '/auth/reset-password')?.body).toEqual({ token: 'abc', password: 'a new password' })
    expect(router.currentRoute.value.name).toBe('account')
  })

  it('shows errors and incomplete links', async () => {
    new FakeApi().error('POST', '/auth/reset-password', 422, 'invalid_token')
    await mountView(ResetPasswordView, { path: '/reset-password?token=old' })
    await type('#password', 'a new password')
    await click('[data-test=submit]')
    expect($('[data-test=error]').text()).toContain('This link is invalid or has expired.')

    await mountView(ResetPasswordView, { path: '/reset-password' })
    expect(text()).toContain('The link is incomplete')
  })
})
