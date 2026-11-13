/** Every IANA time zone the browser knows, for the time zone pickers. */
export function timezones(): string[] {
  return typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : ['Europe/Berlin']
}

/** The browser's time zone: a good default for a new organization. */
export function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Berlin'
}
