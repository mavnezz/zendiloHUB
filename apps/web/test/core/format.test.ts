import { describe, expect, it } from 'vitest'
import {
  EMPTY,
  formatBytes,
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPhoneNumber,
} from '@/core/format'
import { setLocale } from '@/core/i18n/i18n'

describe('format', () => {
  it('formats numbers in the language of the app', () => {
    expect(formatNumber(12000)).toBe('12,000')
    expect(formatNumber(41.666, 1)).toBe('41.7')
    setLocale('de')
    expect(formatNumber(12000)).toBe('12.000')
    expect(formatNumber(41.666, 1)).toBe('41,7')
    expect(formatNumber(null)).toBe(EMPTY)
    expect(formatNumber(Number.NaN)).toBe(EMPTY)
  })

  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(40 * 1024 * 1024)).toBe('40 MB')
    expect(formatBytes(3 * 1024 ** 4)).toBe('3,072 GB')
    expect(formatBytes(undefined)).toBe(EMPTY)
  })

  it('formats dates', () => {
    expect(formatDate('2026-10-22T12:00:00Z')).toBe('Oct 22, 2026')
    expect(formatDateTime('2026-10-22T12:00:00Z')).toMatch(/^Oct 22, 2026/)
    setLocale('de')
    expect(formatDate(new Date('2026-10-22T12:00:00Z'))).toBe('22.10.2026')
    expect(formatDate(null)).toBe(EMPTY)
    expect(formatDateTime(undefined)).toBe(EMPTY)
  })

  it('spaces German phone numbers after the area code and leaves others as they are', () => {
    expect(formatPhoneNumber('+49301234567')).toBe('+49 30 1234567')
    expect(formatPhoneNumber('+491711234567')).toBe('+49 171 1234567')
    expect(formatPhoneNumber('+4312345678')).toBe('+4312345678')
  })

  it('formats durations', () => {
    expect(formatDuration(0)).toBe('0:00')
    expect(formatDuration(65.7)).toBe('1:05')
    expect(formatDuration(3725)).toBe('1:02:05')
    expect(formatDuration(null)).toBe(EMPTY)
    expect(formatDuration(-1)).toBe(EMPTY)
  })
})
