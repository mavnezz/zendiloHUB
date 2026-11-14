import { computed, effectScope, reactive, watch } from 'vue'
import { i18n, setLocale } from '@/core/i18n/i18n'
import { identityApi, type User } from './api'

const state = reactive<{ loaded: boolean; user: User | null }>({ loaded: false, user: null })

/** After a login, a confirmed sign-up or a password reset: the app speaks the account's language. */
function start(user: User | null): void {
  state.user = user
  state.loaded = true
  if (user) {
    setLocale(user.locale)
  }
}

/** Who is logged in. Shared by the whole app. */
export function useSession() {
  return {
    user: computed(() => state.user),
    loaded: computed(() => state.loaded),
    authenticated: computed(() => state.user !== null),
    isAdmin: computed(() => state.user?.role === 'admin'),

    async load(force = false): Promise<void> {
      if (state.loaded && !force) {
        return
      }
      const session = await identityApi.session()
      state.user = session.user
      state.loaded = true
    },

    /** Logs in; with two-factor login it returns the challenge for `completeTwoFactor` instead. */
    async login(email: string, password: string): Promise<string | null> {
      const session = await identityApi.login({ email, password })
      if (session.challenge) {
        return session.challenge
      }
      start(session.user)
      return null
    },

    async completeTwoFactor(challenge: string, code: string): Promise<void> {
      start((await identityApi.loginTwoFactor({ challenge, code: code.trim() })).user)
    },

    start,

    async logout(): Promise<void> {
      try {
        await identityApi.logout()
      } finally {
        state.user = null
      }
    },

    /** After the user edited their own account. */
    replaceUser(user: User): void {
      state.user = user
    },

    /** The session ended (401, account deleted). */
    expire(): void {
      state.user = null
      state.loaded = true
    },

    /** Forget everything, as after a reload (tests). */
    reset(): void {
      state.user = null
      state.loaded = false
    },
  }
}

let syncing = false

/** Switching the language while logged in also switches the language of the account's e-mails. */
export function installLocaleSync(): void {
  if (syncing) {
    return
  }
  syncing = true
  // A detached scope: the watcher lives as long as the app.
  effectScope(true).run(() => {
    watch(
      () => i18n.global.locale.value,
      async (locale) => {
        if (state.user && state.user.locale !== locale) {
          try {
            state.user = await identityApi.updateAccount({ locale })
          } catch {
            // Not important enough to bother the user; the next switch tries again.
          }
        }
      },
    )
  })
}
