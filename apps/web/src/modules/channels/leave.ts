/** Leaves the app for another site (an OAuth provider's sign-in page); a module of its own so tests can replace it. */
export function leaveTo(url: string): void {
  window.location.assign(url)
}
