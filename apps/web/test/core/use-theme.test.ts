import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

async function load(systemDark: boolean, stored?: string) {
  vi.resetModules()
  if (stored) {
    localStorage.setItem('zendilohub.theme', stored)
  }
  const listeners: ((event: { matches: boolean }) => void)[] = []
  vi.stubGlobal('matchMedia', () => ({
    matches: systemDark,
    addEventListener: (_: string, listener: (event: { matches: boolean }) => void) => listeners.push(listener),
  }))
  const { useTheme } = await import('@/core/composables/use-theme')
  return { theme: useTheme(), listeners }
}

describe('useTheme', () => {
  it('follows the system preference by default', async () => {
    const { theme, listeners } = await load(true)
    expect(theme.preference.value).toBe('system')
    expect(theme.dark.value).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    listeners[0]?.({ matches: false })
    await nextTick()
    expect(theme.dark.value).toBe(false)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    vi.unstubAllGlobals()
  })

  it('remembers an explicit choice', async () => {
    const { theme } = await load(false, 'dark')
    expect(theme.dark.value).toBe(true)
    theme.toggle()
    expect(theme.preference.value).toBe('light')
    expect(localStorage.getItem('zendilohub.theme')).toBe('light')
    theme.setPreference('system')
    expect(localStorage.getItem('zendilohub.theme')).toBeNull()
    vi.unstubAllGlobals()
  })

  it('initializes only once', async () => {
    const { theme } = await load(false)
    const { useTheme } = await import('@/core/composables/use-theme')
    expect(useTheme().dark.value).toBe(theme.dark.value)
    vi.unstubAllGlobals()
  })

  it('copes without matchMedia', async () => {
    vi.resetModules()
    vi.stubGlobal('matchMedia', undefined)
    const { useTheme } = await import('@/core/composables/use-theme')
    expect(useTheme().dark.value).toBe(false)
    vi.unstubAllGlobals()
  })
})
