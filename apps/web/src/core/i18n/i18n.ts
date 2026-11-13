import { computed } from 'vue'
import { createI18n } from 'vue-i18n'
import { ApiRequestError } from '../api/http'
import { de } from './messages/de'
import { en } from './messages/en'

export const LOCALES = ['de', 'en'] as const
export type Locale = (typeof LOCALES)[number]

export const LOCALE_STORAGE_KEY = 'zendilohub.locale'

export function isLocale(value: unknown): value is Locale {
  return LOCALES.includes(value as Locale)
}

/** The stored choice, else the browser's preferred language if we have it, else English. */
export function detectLocale(stored: string | null, languages: readonly string[]): Locale {
  if (isLocale(stored)) {
    return stored
  }
  for (const language of languages) {
    const base = language.toLowerCase().split('-')[0]
    if (isLocale(base)) {
      return base
    }
  }
  return 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(
    globalThis.localStorage?.getItem(LOCALE_STORAGE_KEY) ?? null,
    globalThis.navigator?.languages ?? [],
  ),
  fallbackLocale: 'en',
  messages: { en, de },
})

function apply(locale: Locale): void {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
}

apply(i18n.global.locale.value)

export function setLocale(locale: Locale): void {
  apply(locale)
  localStorage.setItem(LOCALE_STORAGE_KEY, locale)
}

export function useLocale() {
  return {
    locale: computed(() => i18n.global.locale.value),
    locales: LOCALES,
    setLocale,
  }
}

/** The text of an error code: one worded for the field it names (`fieldErrors.<code>.<field>`), else the code's. */
function errorKey(code: string, params: Record<string, string | number>): string | null {
  const variant = typeof params.field === 'string' ? `fieldErrors.${code}.${params.field}` : null
  if (variant && i18n.global.te(variant)) {
    return variant
  }
  const key = `errors.${code}`
  return i18n.global.te(key) ? key : null
}

/** A message for the user: API errors are translated by their code, with the API's English text as fallback. */
export function errorText(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const key = errorKey(error.code, error.params)
    return key ? i18n.global.t(key, { status: error.status, ...error.params }) : error.message
  }
  return error instanceof Error ? error.message : String(error)
}

/** The message for an error code the API reported earlier (e.g. stored with an image). */
export function codeText(code: string, params: Record<string, string | number> = {}): string {
  const key = errorKey(code, params)
  return key ? i18n.global.t(key, params) : i18n.global.t('common.error')
}
