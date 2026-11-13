import { describe, expect, it } from 'vitest'
import { i18n } from '@/core/i18n/i18n'
import DeleteAccountCard from '@/modules/identity/components/DeleteAccountCard.vue'
import PasswordCard from '@/modules/identity/components/PasswordCard.vue'
import ProfileCard from '@/modules/identity/components/ProfileCard.vue'
import { useSession } from '@/modules/identity/session'
import { FakeApi } from '../../support/fake-api'
import { user } from '../../support/fixtures'
import { $, click, exists, flushPromises, mountView, type } from '../../support/mount'

describe('account cards', () => {
  it('changes the language of the account and the app', async () => {
    useSession().start(user())
    const api = new FakeApi().on('PATCH', '/account', (request) => ({
      body: user({ locale: (request.body as { locale: 'de' | 'en' }).locale }),
    }))
    await mountView(ProfileCard, { path: '/account' })
    expect(($('#account-email').element as HTMLInputElement).value).toBe('ada@example.org')
    await click('[data-test=option-de]')
    expect(api.last('PATCH', '/account')?.body).toEqual({ locale: 'de' })
    expect(i18n.global.locale.value).toBe('de')
    expect(useSession().user.value?.locale).toBe('de')
  })

  it('reports a failed language change', async () => {
    useSession().start(user())
    new FakeApi().error('PATCH', '/account', 500, 'internal_error')
    await mountView(ProfileCard, { path: '/account' })
    await click('[data-test=option-de]')
    expect(useSession().user.value?.locale).toBe('en')
  })

  it('changes the password', async () => {
    useSession().start(user())
    const api = new FakeApi().error('POST', '/account/password', 422, 'invalid_current_password')
    await mountView(PasswordCard, { path: '/account' })
    await type('#current-password', 'wrong password')
    await type('#new-password', 'a new password')
    await click('[data-test=change-password]')
    expect($('[data-test=error]').text()).toContain('The password is wrong.')

    api.on('POST', '/account/password', { status: 204 })
    await type('#current-password', 'correct horse battery')
    await click('[data-test=change-password]')
    expect(api.last('POST', '/account/password')?.body).toEqual({
      current_password: 'correct horse battery',
      new_password: 'a new password',
    })
    expect(exists('[data-test=error]')).toBe(false)
    expect(($('#current-password').element as HTMLInputElement).value).toBe('')
  })

  it('deletes the account after confirming with the password', async () => {
    useSession().start(user())
    const api = new FakeApi().on('POST', '/account/delete', { status: 204 })
    const { router } = await mountView(DeleteAccountCard, { path: '/account' })
    await click('[data-test=delete-account]')
    await type('[data-test=delete-password]', 'correct horse battery')
    await click('[data-test=confirm]')
    await flushPromises()
    expect(api.last('POST', '/account/delete')?.body).toEqual({ password: 'correct horse battery' })
    expect(useSession().authenticated.value).toBe(false)
    expect(router.currentRoute.value.name).toBe('start')
  })

  it('keeps the dialog open when the password is wrong', async () => {
    useSession().start(user())
    new FakeApi().error('POST', '/account/delete', 422, 'invalid_current_password')
    await mountView(DeleteAccountCard, { path: '/account' })
    await click('[data-test=delete-account]')
    await type('[data-test=delete-password]', 'wrong')
    await click('[data-test=confirm]')
    expect(useSession().authenticated.value).toBe(true)
    expect(exists('[data-test=delete-password]')).toBe(true)
  })
})
