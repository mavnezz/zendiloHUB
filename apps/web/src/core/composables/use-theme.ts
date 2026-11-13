import { computed, effectScope, ref, watch } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'zendilohub.theme'

const preference = ref<ThemePreference>(read())
const systemDark = ref(false)
let initialized = false

function read(): ThemePreference {
  const stored = globalThis.localStorage?.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

function initialize(): void {
  if (initialized) {
    return
  }
  initialized = true
  const media = globalThis.matchMedia?.('(prefers-color-scheme: dark)')
  systemDark.value = media?.matches ?? false
  media?.addEventListener?.('change', (event) => {
    systemDark.value = event.matches
  })
  // A detached scope: the watcher must outlive the component that happened to call useTheme() first.
  effectScope(true).run(() => {
    watch(
      () => preference.value === 'dark' || (preference.value === 'system' && systemDark.value),
      (dark) => document.documentElement.classList.toggle('dark', dark),
      { immediate: true },
    )
  })
}

/** Light/dark mode: follows the system unless the user picked one. */
export function useTheme() {
  initialize()
  const dark = computed(() => preference.value === 'dark' || (preference.value === 'system' && systemDark.value))

  function setPreference(value: ThemePreference): void {
    preference.value = value
    if (value === 'system') {
      localStorage.removeItem(STORAGE_KEY)
    } else {
      localStorage.setItem(STORAGE_KEY, value)
    }
  }

  return {
    preference: computed(() => preference.value),
    dark,
    setPreference,
    toggle: () => setPreference(dark.value ? 'light' : 'dark'),
  }
}
