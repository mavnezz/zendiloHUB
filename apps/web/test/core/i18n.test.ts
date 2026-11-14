import { baseCompile } from '@intlify/message-compiler'
import { describe, expect, it } from 'vitest'
import { ApiRequestError } from '@/core/api/http'
import { codeText, detectLocale, errorText, i18n, LOCALE_STORAGE_KEY, setLocale, useLocale } from '@/core/i18n/i18n'
import { de } from '@/core/i18n/messages/de'
import { en } from '@/core/i18n/messages/en'

function keys(messages: object, prefix = ''): string[] {
  return Object.entries(messages).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null ? keys(value as object, `${prefix}${key}.`) : [`${prefix}${key}`],
  )
}

describe('detectLocale', () => {
  it('prefers the stored choice', () => {
    expect(detectLocale('de', ['en-US'])).toBe('de')
  })

  it('falls back to the browser languages, then English', () => {
    expect(detectLocale(null, ['fr-FR', 'de-AT', 'en'])).toBe('de')
    expect(detectLocale('klingon', ['EN-GB'])).toBe('en')
    expect(detectLocale(null, ['fr', 'it'])).toBe('en')
    expect(detectLocale(null, [])).toBe('en')
  })
})

describe('setLocale', () => {
  it('switches the language, remembers it and updates the document', () => {
    const { locale } = useLocale()
    setLocale('de')
    expect(locale.value).toBe('de')
    expect(i18n.global.t('nav.logout')).toBe('Abmelden')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('de')
    expect(document.documentElement.lang).toBe('de')
  })
})

function texts(messages: object, prefix = ''): [string, string][] {
  return Object.entries(messages).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null
      ? texts(value as object, `${prefix}${key}.`)
      : [[`${prefix}${key}`, String(value)] as [string, string]],
  )
}

describe('messages', () => {
  it('compiles every text (a bare @, | or { breaks the page that shows it)', () => {
    const broken = [...texts(en), ...texts(de)].filter(([, text]) => {
      let failed = false
      baseCompile(text, { onError: () => (failed = true) })
      return failed
    })
    expect(broken.map(([key]) => key)).toEqual([])
  })

  it('has every text in German and English', () => {
    expect(keys(de)).toEqual(keys(en))
  })
})

describe('errorText', () => {
  it('translates API errors by their code, with parameters', () => {
    setLocale('de')
    expect(errorText(new ApiRequestError(502, 'http_error', 'Request failed'))).toBe(
      'Die Anfrage ist fehlgeschlagen (Status 502).',
    )
    setLocale('en')
    expect(errorText(new ApiRequestError(0, 'network_error', 'down'))).toContain('The server is not reachable')
  })

  it('words errors for the field they name, else by their code', () => {
    i18n.global.mergeLocaleMessage('en', {
      fieldErrors: { invalid_email: { invitee: 'Check the address of {name}.' } },
    })
    expect(errorText(new ApiRequestError(422, 'invalid_email', 'x', { field: 'invitee', name: 'Bob' }))).toBe(
      'Check the address of Bob.',
    )
    expect(errorText(new ApiRequestError(422, 'invalid_email', 'x', { field: 'something' }))).toBe(
      'This is not a valid e-mail address.',
    )
    expect(codeText('invalid_email', { field: 'invitee', name: 'Eve' })).toBe('Check the address of Eve.')
    expect(codeText('last_owner')).toBe('An organization needs at least one owner.')
    expect(codeText('never_heard_of')).toBe('Something went wrong')
  })

  it("falls back to the API's message and to other errors' messages", () => {
    expect(errorText(new ApiRequestError(409, 'something_new', 'Something new happened'))).toBe(
      'Something new happened',
    )
    expect(errorText(new Error('boom'))).toBe('boom')
    expect(errorText('plain')).toBe('plain')
  })
})
