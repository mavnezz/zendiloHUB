import { i18n } from './i18n/i18n'

/** Formatting in the language the user picked (decimal comma in German). */
function locale(): string {
  return i18n.global.locale.value
}

export const EMPTY = '–'

export function formatNumber(value: number | null | undefined, fractionDigits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return EMPTY
  }
  return new Intl.NumberFormat(locale(), { maximumFractionDigits: fractionDigits }).format(value)
}

/** 0.625 → 63 % (German) or 63% (English). */
export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) {
    return EMPTY
  }
  return new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 0 }).format(ratio)
}

const UNITS = ['B', 'KB', 'MB', 'GB']

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) {
    return EMPTY
  }
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit++
  }
  return `${formatNumber(value, unit === 0 ? 0 : 1)} ${UNITS[unit]}`
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) {
    return EMPTY
  }
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium' }).format(new Date(value))
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) {
    return EMPTY
  }
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

/** +49301234567 → +49 30 1234567: readable without knowing every country's area codes (spaces after the code). */
export function formatPhoneNumber(e164: string): string {
  const german = /^\+49(1[5-7]\d|[2-9]\d)(\d+)$/.exec(e164)
  if (german) {
    return `+49 ${german[1]} ${german[2]}`
  }
  return e164
}

/** 65 → 1:05, 3725 → 1:02:05. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return EMPTY
  }
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}
