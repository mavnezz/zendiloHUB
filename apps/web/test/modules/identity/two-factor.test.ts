import { describe, expect, it, vi } from 'vitest'
import TwoFactorCard from '@/modules/identity/components/TwoFactorCard.vue'
import AdminUsersView from '@/modules/identity/views/AdminUsersView.vue'
import LoginView from '@/modules/identity/views/LoginView.vue'
import ResetPasswordView from '@/modules/identity/views/ResetPasswordView.vue'
import { useSession } from '@/modules/identity/session'
import { FakeApi } from '../../support/fake-api'
import { user } from '../../support/fixtures'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'

const CODES = ['abcd-efgh', 'jkmn-pqrs']

describe('two-factor login', () => {
  it('asks for the code after the password', async () => {
    const api = new FakeApi()
      .json('POST', '/auth/login', { user: null, challenge: 'c1' })
      .error('POST', '/auth/login/two-factor', 422, 'invalid_two_factor_code')
    const { router } = await mountView(LoginView, { path: '/login?redirect=/account' })
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    expect(useSession().user.value).toBeNull()
    expect(text()).toContain('Enter the code from your authenticator app.')
    expect(text()).toContain('ada@example.org')

    await type('[data-test=code]', '000000')
    await click('[data-test=verify]')
    expect($('[data-test=error]').text()).toContain('The code is wrong or was used already.')
    expect(($('[data-test=code]').element as HTMLInputElement).value).toBe('')

    api.json('POST', '/auth/login/two-factor', { user: user() })
    await type('[data-test=code]', ' 123456 ')
    await click('[data-test=verify]')
    expect(api.last('POST', '/auth/login/two-factor')?.body).toEqual({ challenge: 'c1', code: '123456' })
    expect(useSession().user.value?.email).toBe('ada@example.org')
    expect(router.currentRoute.value.fullPath).toBe('/account')
  })

  it('goes back to the password', async () => {
    new FakeApi().json('POST', '/auth/login', { user: null, challenge: 'c1' })
    await mountView(LoginView, { path: '/login' })
    await type('#email', 'ada@example.org')
    await type('#password', 'correct horse battery')
    await click('[data-test=submit]')
    await click('[data-test=back]')
    expect(exists('[data-test=code]')).toBe(false)
    expect(($('#password').element as HTMLInputElement).value).toBe('')
  })

  it('asks for the code after a password reset', async () => {
    const api = new FakeApi()
      .json('POST', '/auth/reset-password', { user: null, challenge: 'c2' })
      .json('POST', '/auth/login/two-factor', { user: user() })
    const { router } = await mountView(ResetPasswordView, { path: '/reset-password?token=abc' })
    await type('#password', 'a new password')
    await click('[data-test=submit]')
    expect(router.currentRoute.value.name).not.toBe('account')
    await type('[data-test=code]', 'abcd-efgh')
    await click('[data-test=verify]')
    expect(api.last('POST', '/auth/login/two-factor')?.body).toEqual({ challenge: 'c2', code: 'abcd-efgh' })
    expect(router.currentRoute.value.name).toBe('account')
  })

  it('leaves the reset for the login', async () => {
    new FakeApi().json('POST', '/auth/reset-password', { user: null, challenge: 'c2' })
    const { router } = await mountView(ResetPasswordView, { path: '/reset-password?token=abc' })
    await type('#password', 'a new password')
    await click('[data-test=submit]')
    await click('[data-test=back]')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
  })
})

describe('TwoFactorCard', () => {
  it('sets up two-factor login with the QR code and shows the recovery codes once', async () => {
    useSession().start(user())
    const api = new FakeApi()
      .json('GET', '/account/two-factor', { enabled: false, recovery_codes_left: 0 })
      .error('POST', '/account/two-factor/setup', 422, 'invalid_current_password')
    await mountView(TwoFactorCard, { path: '/account' })
    expect($('[data-test=two-factor-state]').text()).toBe('Off')

    await click('[data-test=setup-two-factor]')
    expect($('[data-test=confirm]').attributes('disabled')).toBeDefined()
    await type('[data-test=two-factor-password]', 'wrong')
    await click('[data-test=confirm]')
    expect(exists('[data-test=two-factor-setup]')).toBe(false)

    api.json('POST', '/account/two-factor/setup', {
      secret: 'JBSWY3DPEHPK3PXP',
      uri: 'otpauth://totp/zendiloHUB:ada@example.org?secret=JBSWY3DPEHPK3PXP&issuer=zendiloHUB',
    })
    await type('[data-test=two-factor-password]', 'correct horse battery')
    await click('[data-test=confirm]')
    await flushPromises()
    expect(api.last('POST', '/account/two-factor/setup')?.body).toEqual({ password: 'correct horse battery' })
    expect($('[data-test=secret]').text()).toBe('JBSWY3DPEHPK3PXP')
    expect($('[data-test=qr]').attributes('src')).toMatch(/^data:image\/svg\+xml/)

    api.error('POST', '/account/two-factor/enable', 422, 'invalid_two_factor_code')
    await type('[data-test=setup-code]', '000000')
    await click('[data-test=enable]')
    expect($('[data-test=error]').text()).toContain('The code is wrong')

    api
      .json('POST', '/account/two-factor/enable', { recovery_codes: CODES })
      .json('GET', '/account/two-factor', { enabled: true, recovery_codes_left: 2 })
    await type('[data-test=setup-code]', '123 456')
    await click('[data-test=enable]')
    expect(api.last('POST', '/account/two-factor/enable')?.body).toEqual({ code: '123456' })
    expect($('[data-test=recovery-codes]').text()).toContain('abcd-efgh')
    expect(useSession().user.value?.two_factor).toBe(true)

    const writeText = vi.fn(() => Promise.resolve())
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await click('[data-test=copy-codes]')
    expect(writeText).toHaveBeenCalledWith('abcd-efgh\njkmn-pqrs')
    const created = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:codes')
    const revoked = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    await click('[data-test=download-codes]')
    expect(created).toHaveBeenCalled()
    expect(revoked).toHaveBeenCalledWith('blob:codes')
    await click('[data-test=codes-done]')
    expect(exists('[data-test=recovery-codes]')).toBe(false)
    expect($('[data-test=codes-left]').text()).toBe('2 recovery codes left')
  })

  it('cancels a setup', async () => {
    useSession().start(user())
    new FakeApi()
      .json('GET', '/account/two-factor', { enabled: false, recovery_codes_left: 0 })
      .json('POST', '/account/two-factor/setup', { secret: 'S', uri: 'otpauth://totp/x?secret=S' })
    await mountView(TwoFactorCard, { path: '/account' })
    await click('[data-test=setup-two-factor]')
    await type('[data-test=two-factor-password]', 'correct horse battery')
    await click('[data-test=confirm]')
    await flushPromises()
    await click('[data-test=cancel-setup]')
    expect(exists('[data-test=two-factor-setup]')).toBe(false)
    expect(exists('[data-test=setup-two-factor]')).toBe(true)
  })

  it('renews the recovery codes and turns two-factor login off', async () => {
    useSession().start(user({ two_factor: true }))
    const api = new FakeApi()
      .json('GET', '/account/two-factor', { enabled: true, recovery_codes_left: 3 })
      .json('POST', '/account/two-factor/recovery-codes', { recovery_codes: CODES })
      .on('POST', '/account/two-factor/disable', { status: 204 })
    await mountView(TwoFactorCard, { path: '/account' })
    expect($('[data-test=two-factor-state]').text()).toBe('On')
    expect($('[data-test=codes-left]').text()).toBe('3 recovery codes left')

    await click('[data-test=renew-codes]')
    await type('[data-test=two-factor-password]', 'correct horse battery')
    await click('[data-test=confirm]')
    await flushPromises()
    expect(api.last('POST', '/account/two-factor/recovery-codes')?.body).toEqual({ password: 'correct horse battery' })
    expect($$('[data-test=recovery-codes] li')).toHaveLength(2)
    await click('[data-test=codes-done]')

    api.json('GET', '/account/two-factor', { enabled: false, recovery_codes_left: 0 })
    await click('[data-test=disable-two-factor]')
    await type('[data-test=two-factor-password]', 'correct horse battery')
    await click('[data-test=confirm]')
    await flushPromises()
    expect(api.last('POST', '/account/two-factor/disable')?.body).toEqual({ password: 'correct horse battery' })
    expect($('[data-test=two-factor-state]').text()).toBe('Off')
    expect(useSession().user.value?.two_factor).toBe(false)
  })

  it('shows a load error', async () => {
    useSession().start(user())
    new FakeApi().error('GET', '/account/two-factor', 500, 'internal_error')
    await mountView(TwoFactorCard, { path: '/account' })
    expect(exists('[data-test=error]')).toBe(true)
    expect(exists('[data-test=setup-two-factor]')).toBe(false)
  })
})

describe('AdminUsersView two-factor', () => {
  it('resets the two-factor login of a user', async () => {
    const grace = user({ id: 'u0', email: 'grace@example.org', role: 'admin', two_factor: true })
    const ada = user({ id: 'u1', email: 'ada@example.org', two_factor: true })
    useSession().start(grace)
    const api = new FakeApi()
      .json('GET', '/admin/users', { items: [grace, ada], total: 2 })
      .on('DELETE', '/admin/users/u1/two-factor', { status: 204 })
    await mountView(AdminUsersView, { path: '/admin/users' })
    const rows = $$('[data-test=user-row]')
    expect(rows[0]?.find('[data-test=two-factor-badge]').exists()).toBe(true)
    expect(rows[0]?.find('[data-test=reset-two-factor]').exists()).toBe(false)
    await click('[data-test=reset-two-factor]')
    expect(text()).toContain('Reset the two-factor login of ada@example.org?')
    await click('[data-test=confirm]')
    await flushPromises()
    expect(api.calls('DELETE', '/admin/users/u1/two-factor')).toHaveLength(1)
  })
})
