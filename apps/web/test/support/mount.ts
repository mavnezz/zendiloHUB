import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, reactive, type Component } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { i18n } from '@/core/i18n/i18n'

const mounted: VueWrapper[] = []

/** Unmounts everything mountView mounted, then empties the document. */
export function unmountAll(): void {
  for (const wrapper of mounted.splice(0)) {
    wrapper.unmount()
  }
  document.body.innerHTML = ''
}

const Page = defineComponent({ name: 'TestPage', render: () => h('div', { 'data-test': 'page' }) })

/** Every named route of the app, each rendering an empty page. */
export function testRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'start', component: Page },
      ...[
        'login',
        'register',
        'verify-email',
        'forgot-password',
        'reset-password',
        'account',
        'onboarding',
        'invitations',
        'imprint',
        'privacy',
        'terms',
      ].map((name) => ({ path: `/${name}`, name: name === 'invitations' ? 'invitation' : name, component: Page })),
      { path: '/setup', name: 'setup', component: Page },
      ...['overview', 'team', 'roles', 'settings', 'audit'].map((name) => ({
        path: `/t/:tenantId/${name}`,
        name,
        component: Page,
      })),
      { path: '/t/:tenantId/api-keys', name: 'apiKeys', component: Page },
      { path: '/admin/tenants', name: 'admin-tenants', component: Page },
      { path: '/admin/users', name: 'admin-users', component: Page },
      { path: '/admin/audit-log', name: 'admin-audit', component: Page },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: Page },
    ],
  })
}

export interface MountOptions {
  props?: Record<string, unknown>
  router?: Router
  path?: string
  /** Components to replace (e.g. a canvas that needs a real browser). */
  stubs?: Record<string, Component | boolean>
}

/** Mounts a view or component the way the app renders it. */
export async function mountView(component: Component, options: MountOptions = {}) {
  const router = options.router ?? testRouter()
  await router.push(options.path ?? '/')
  await router.isReady()
  /** Change these to update the props of the mounted component. */
  const props = reactive<Record<string, unknown>>({ ...options.props })
  const Host = defineComponent({ setup: () => () => h(component, props) })
  const wrapper = mount(Host, { global: { plugins: [router, i18n], stubs: options.stubs }, attachTo: document.body })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router, props }
}

/** Queries the whole document, including dialogs teleported to <body>. */
export function $(selector: string): DOMWrapper<Element> {
  const element = document.querySelector(selector)
  if (!element) {
    throw new Error(`Nothing matches ${selector}`)
  }
  return new DOMWrapper(element)
}

export function $$(selector: string): DOMWrapper<Element>[] {
  return [...document.querySelectorAll(selector)].map((element) => new DOMWrapper(element))
}

export function exists(selector: string): boolean {
  return document.querySelector(selector) !== null
}

export function text(): string {
  return document.body.textContent ?? ''
}

/** Types into an input inside the document. */
export async function type(selector: string, value: string): Promise<void> {
  await $(selector).setValue(value)
}

export async function click(selector: string): Promise<void> {
  await $(selector).trigger('click')
  await flushPromises()
}

export { flushPromises }

/** Runs a composable inside a mounted component (for lifecycle hooks); returns its result and the wrapper. */
export function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result: T | undefined
  const Host = defineComponent({
    setup() {
      result = composable()
      return () => h('div')
    },
  })
  const wrapper = mount(Host, { global: { plugins: [i18n] } })
  return { result: result as T, unmount: () => wrapper.unmount() }
}
