import { describe, expect, it } from 'vitest'
import { useSession } from '@/modules/identity/session'
import type { TenantRole } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import AdminTenantsView from '@/modules/tenancy/views/AdminTenantsView.vue'
import InvitationView from '@/modules/tenancy/views/InvitationView.vue'
import OnboardingView from '@/modules/tenancy/views/OnboardingView.vue'
import RolesView from '@/modules/tenancy/views/RolesView.vue'
import TeamView from '@/modules/tenancy/views/TeamView.vue'
import TenantSettingsView from '@/modules/tenancy/views/TenantSettingsView.vue'
import { FakeApi } from '../../support/fake-api'
import { invitation, member, ROLE_MATRIX, tenant, TENANT_ID, user } from '../../support/fixtures'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const BASE = `/tenants/${TENANT_ID}`

function inTenant(role: TenantRole = 'owner'): void {
  useSession().start(user())
  const tenants = useTenants()
  tenants.put(tenant({ role }))
  tenants.select(TENANT_ID)
}

const PREVIEW = {
  tenant_name: 'Acme GmbH',
  email: 'ada@example.org',
  role: 'manager',
  expires_at: '2026-10-29T12:00:00Z',
}

describe('OnboardingView', () => {
  it('creates the organization and opens it', async () => {
    const api = new FakeApi().json('POST', '/tenants', tenant({ name: 'Acme GmbH' }), 201)
    const { router } = await mountView(OnboardingView, { path: '/onboarding' })
    expect($('[data-test=submit]').attributes('disabled')).toBeDefined()
    await type('#name', 'Acme GmbH')
    await $('#timezone').setValue('Europe/Vienna')
    await $('#language').setValue('de')
    await click('[data-test=submit]')
    expect(api.last('POST', '/tenants')?.body).toEqual({ name: 'Acme GmbH', timezone: 'Europe/Vienna', locale: 'de' })
    expect(router.currentRoute.value.fullPath).toBe(`/t/${TENANT_ID}/overview`)
    expect(useTenants().tenants.value.map((each) => each.name)).toEqual(['Acme GmbH'])
  })

  it('explains why it failed', async () => {
    new FakeApi().error('POST', '/tenants', 422, 'invalid_tenant_name')
    await mountView(OnboardingView, { path: '/onboarding' })
    await type('#name', 'x')
    await click('[data-test=submit]')
    expect($('[data-test=error]').text()).toContain('The name must have between 1 and')
  })
})

describe('TeamView', () => {
  const members = [
    member(),
    member({ user_id: 'u2', email: 'bob@example.org', role: 'agent' }),
    member({ user_id: 'u3', email: 'carol@example.org', role: 'owner' }),
  ]

  function api(): FakeApi {
    return new FakeApi().json('GET', `${BASE}/members`, members).json('GET', `${BASE}/invitations`, [invitation()])
  }

  it('lists the members and open invitations', async () => {
    inTenant()
    api()
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    expect($$('[data-test=member]')).toHaveLength(3)
    expect($$('[data-test=member]')[0]?.text()).toContain('you')
    expect($('[data-test=invitation]').text()).toContain('bob@example.org')
    expect(exists('[data-test=leave]')).toBe(true)
  })

  it('changes roles, removes members and revokes invitations', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api()
      .json('PATCH', `${BASE}/members/u2`, member({ user_id: 'u2', email: 'bob@example.org', role: 'manager' }))
      .on('DELETE', `${BASE}/members/u2`, { status: 204 })
      .on('DELETE', `${BASE}/invitations/i1`, { status: 204 })
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })

    await $('[data-test="role-bob@example.org"] select').setValue('manager')
    await flushPromises()
    expect(fake.last('PATCH', `${BASE}/members/u2`)?.body).toEqual({ role: 'manager' })
    expect(toasts.success()).toContain('bob@example.org is now Manager.')

    await click('[data-test="remove-bob@example.org"]')
    expect(text()).toContain('Remove bob@example.org?')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/members/u2`)).toHaveLength(1)

    await click('[data-test="revoke-bob@example.org"]')
    expect(fake.calls('DELETE', `${BASE}/invitations/i1`)).toHaveLength(1)
    expect(fake.calls('GET', `${BASE}/invitations`).length).toBeGreaterThan(1)
  })

  it('reports failed role changes and reloads the own permissions after changing the own role', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api()
      .error('PATCH', `${BASE}/members/u2`, 409, 'last_owner')
      .json('PATCH', `${BASE}/members/u1`, member({ role: 'admin' }))
      .json('GET', '/tenants', [tenant({ role: 'admin' })])
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    await $('[data-test="role-bob@example.org"] select').setValue('admin')
    await flushPromises()
    expect(toasts.error()).toContain('An organization needs at least one owner.')
    await $('[data-test="role-ada@example.org"] select').setValue('admin')
    await flushPromises()
    expect(fake.calls('GET', '/tenants')).toHaveLength(1)
    expect(useTenants().current.value?.role).toBe('admin')
  })

  it('lets members leave', async () => {
    inTenant()
    api().on('DELETE', `${BASE}/members/u1`, { status: 204 })
    const { router } = await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    await click('[data-test=leave]')
    expect(text()).toContain('Leave Acme GmbH?')
    await click('[data-test=confirm]')
    expect(router.currentRoute.value.name).toBe('start')
    expect(useTenants().tenants.value).toEqual([])
  })

  it('invites people', async () => {
    const toasts = spyToasts()
    inTenant()
    const fake = api().json('POST', `${BASE}/invitations`, invitation({ email: 'dan@example.org' }), 201)
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    await click('[data-test=invite]')
    expect(text()).toContain('Owner – Full control')
    await type('#invite-email', 'dan@example.org')
    await $('#invite-role').setValue('admin')
    await click('[data-test=invite-submit]')
    expect(fake.last('POST', `${BASE}/invitations`)?.body).toEqual({ email: 'dan@example.org', role: 'admin' })
    expect(toasts.success()).toContain('Invitation sent to dan@example.org.')
  })

  it('shows why an invitation failed', async () => {
    inTenant('admin')
    api().error('POST', `${BASE}/invitations`, 409, 'already_member')
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    await click('[data-test=invite]')
    // Admins cannot invite owners.
    expect(text()).not.toContain('Owner – Full control')
    await type('#invite-email', 'bob@example.org')
    await click('[data-test=invite-submit]')
    expect($('[data-test=error]').text()).toContain('This person is already a member.')
  })

  it('shows agents the team without management', async () => {
    inTenant('agent')
    const fake = new FakeApi().json('GET', `${BASE}/members`, members)
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    expect(exists('[data-test=invite]')).toBe(false)
    expect(exists('[data-test=no-invitations]')).toBe(false)
    expect(exists('select')).toBe(false)
    expect(fake.calls('GET', `${BASE}/invitations`)).toHaveLength(0)
  })

  it('shows admins no controls for owners and an empty invitation list', async () => {
    inTenant('admin')
    new FakeApi().json('GET', `${BASE}/members`, members).json('GET', `${BASE}/invitations`, [])
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    expect(exists('[data-test="role-carol@example.org"]')).toBe(false)
    expect(exists('[data-test="remove-carol@example.org"]')).toBe(false)
    expect(exists('[data-test="role-bob@example.org"]')).toBe(true)
    expect($('[data-test=no-invitations]').text()).toContain('No open invitations.')
  })

  it('reports a failing member list', async () => {
    inTenant()
    new FakeApi().error('GET', `${BASE}/members`, 500, 'internal_error').json('GET', `${BASE}/invitations`, [])
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    expect($('[data-test=error]').text()).toContain('Something went wrong on our side')
  })

  it('reports a failing revocation', async () => {
    const toasts = spyToasts()
    inTenant()
    api().error('DELETE', `${BASE}/invitations/i1`, 404, 'invitation_not_found')
    await mountView(TeamView, { path: `/t/${TENANT_ID}/team` })
    await click('[data-test="revoke-bob@example.org"]')
    expect(toasts.error()).toContain('The invitation does not exist.')
  })
})

describe('RolesView', () => {
  it('shows what each role may do', async () => {
    inTenant('manager')
    new FakeApi().json('GET', '/roles', ROLE_MATRIX)
    await mountView(RolesView, { path: `/t/${TENANT_ID}/roles` })
    expect($('[data-test=role-card-manager]').classes()).toContain('border-primary')
    expect($('[data-test=permission-tenant\\.delete]').text()).toContain('Delete the organization')
    expect($('[data-test=permission-tenant\\.delete]').findAll('[data-test=allowed]')).toHaveLength(1)
    expect($('[data-test=permission-audit\\.view]').findAll('[data-test=allowed]')).toHaveLength(2)
    expect(text()).toContain('Audit log')
  })

  it('reports a failure', async () => {
    inTenant()
    new FakeApi().error('GET', '/roles', 500, 'internal_error')
    await mountView(RolesView, { path: `/t/${TENANT_ID}/roles` })
    expect(exists('[data-test=error]')).toBe(true)
  })
})

describe('TenantSettingsView', () => {
  it('saves name, time zone and language', async () => {
    const toasts = spyToasts()
    inTenant()
    const api = new FakeApi().json('PATCH', BASE, tenant({ name: 'Acme AG', timezone: 'Europe/Vienna', locale: 'en' }))
    await mountView(TenantSettingsView, { path: `/t/${TENANT_ID}/settings` })
    await type('#name', 'Acme AG')
    await $('#timezone').setValue('Europe/Vienna')
    await $('#language').setValue('en')
    await click('[data-test=save]')
    expect(api.last('PATCH', BASE)?.body).toEqual({ name: 'Acme AG', timezone: 'Europe/Vienna', locale: 'en' })
    expect(useTenants().current.value?.name).toBe('Acme AG')
    expect(toasts.success()).toContain('The settings were saved.')
  })

  it('shows why saving failed', async () => {
    inTenant()
    new FakeApi().error('PATCH', BASE, 422, 'invalid_timezone')
    await mountView(TenantSettingsView, { path: `/t/${TENANT_ID}/settings` })
    await click('[data-test=save]')
    expect($('[data-test=error]').text()).toContain('This is not a known time zone.')
  })

  it('deletes the organization after typing its name', async () => {
    inTenant()
    const api = new FakeApi().on('DELETE', BASE, { status: 204 })
    const { router } = await mountView(TenantSettingsView, { path: `/t/${TENANT_ID}/settings` })
    await click('[data-test=delete]')
    expect($('[data-test=confirm]').attributes('disabled')).toBeDefined()
    await type('[data-test=delete-confirmation]', 'Acme GmbH')
    await click('[data-test=confirm]')
    expect(api.calls('DELETE', BASE)).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('start')
    expect(useTenants().tenants.value).toEqual([])
  })

  it('offers the deletion to owners only', async () => {
    inTenant('admin')
    await mountView(TenantSettingsView, { path: `/t/${TENANT_ID}/settings` })
    expect(exists('[data-test=delete]')).toBe(false)
  })
})

describe('InvitationView', () => {
  it('needs the token from the e-mail', async () => {
    new FakeApi().json('GET', '/auth/session', { user: null })
    await mountView(InvitationView, { path: '/invitations' })
    expect($('[data-test=error]').text()).toContain('The link is incomplete')
  })

  it('asks visitors to log in or sign up and remembers the invitation', async () => {
    new FakeApi().json('GET', '/auth/session', { user: null }).json('POST', '/invitations/preview', PREVIEW)
    await mountView(InvitationView, { path: '/invitations?token=secret' })
    expect($('[data-test=invitation-text]').text()).toBe('You are invited to join Acme GmbH as Manager.')
    expect($('[data-test=login]').attributes('href')).toBe('/login?redirect=/invitations?token=secret')
    expect(localStorage.getItem('zendilohub.pending-invitation')).toBe('secret')
  })

  it('lets the invited account join', async () => {
    useSession().start(user())
    const api = new FakeApi()
      .json('POST', '/invitations/preview', PREVIEW)
      .json('POST', '/invitations/accept', tenant({ role: 'manager' }))
    const { router } = await mountView(InvitationView, { path: '/invitations?token=secret' })
    await click('[data-test=accept]')
    expect(api.last('POST', '/invitations/accept')?.body).toEqual({ token: 'secret' })
    expect(router.currentRoute.value.fullPath).toBe(`/t/${TENANT_ID}/overview`)
    expect(useTenants().tenants.value[0]?.role).toBe('manager')
  })

  it('shows why joining failed', async () => {
    useSession().start(user())
    new FakeApi()
      .json('POST', '/invitations/preview', PREVIEW)
      .error('POST', '/invitations/accept', 422, 'invalid_invitation')
    await mountView(InvitationView, { path: '/invitations?token=secret' })
    await click('[data-test=accept]')
    expect($('[data-test=error]').text()).toContain('This invitation is invalid or has expired.')
  })

  it('asks another account to switch', async () => {
    useSession().start(user({ email: 'eve@example.org' }))
    new FakeApi().json('POST', '/invitations/preview', PREVIEW).on('POST', '/auth/logout', { status: 204 })
    const { router } = await mountView(InvitationView, { path: '/invitations?token=secret' })
    expect($('[data-test=other-account]').text()).toContain('You are logged in as eve@example.org')
    await click('[data-test=switch-account]')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/invitations?token=secret')
  })

  it('explains invalid invitations', async () => {
    new FakeApi()
      .json('GET', '/auth/session', { user: null })
      .error('POST', '/invitations/preview', 422, 'invalid_invitation')
    await mountView(InvitationView, { path: '/invitations?token=old' })
    expect($('[data-test=error]').text()).toContain('This invitation is invalid or has expired.')
  })
})

describe('AdminTenantsView', () => {
  const page = {
    items: [
      { ...tenant(), member_count: 3 },
      {
        ...tenant({ id: '00000000-0000-7000-8000-000000000002', name: 'Beta AG', status: 'suspended' }),
        member_count: 1,
      },
    ],
    total: 2,
  }

  it('lists the organizations and suspends or reactivates them', async () => {
    const toasts = spyToasts()
    const api = new FakeApi().json('GET', '/admin/tenants', page).json('PATCH', /\/admin\/tenants\/.+/, tenant())
    await mountView(AdminTenantsView, { path: '/admin/tenants' })
    expect($$('[data-test=tenant]')).toHaveLength(2)
    expect($('[data-test=count]').text()).toBe('2 organizations')
    await click('[data-test="toggle-Acme GmbH"]')
    expect(api.last('PATCH', `/admin/tenants/${TENANT_ID}`)?.body).toEqual({ status: 'suspended' })
    expect(toasts.success()).toContain('Acme GmbH was suspended.')
    await click('[data-test="toggle-Beta AG"]')
    expect(api.last('PATCH', '/admin/tenants/00000000-0000-7000-8000-000000000002')?.body).toEqual({ status: 'active' })
    expect(toasts.success()).toContain('Beta AG is active again.')
  })

  it('searches and pages', async () => {
    const api = new FakeApi().json('GET', '/admin/tenants', { ...page, total: 120 })
    await mountView(AdminTenantsView, { path: '/admin/tenants' })
    await click('[data-test=next]')
    expect(api.last('GET', '/admin/tenants')?.query.offset).toBe('50')
    await click('[data-test=previous]')
    expect(api.last('GET', '/admin/tenants')?.query.offset).toBe('0')
    await type('[data-test=search]', 'acme')
    await new Promise((resolve) => setTimeout(resolve, 300))
    await flushPromises()
    expect(api.last('GET', '/admin/tenants')?.query.q).toBe('acme')
  })

  it('reports failures', async () => {
    new FakeApi()
      .json('GET', '/admin/tenants', { items: [], total: 0 })
      .error('PATCH', /\/admin\/tenants\/.+/, 404, 'tenant_not_found')
    await mountView(AdminTenantsView, { path: '/admin/tenants' })
    expect(text()).toContain('No organizations found.')
  })

  it('reports a failing status change', async () => {
    const toasts = spyToasts()
    new FakeApi().json('GET', '/admin/tenants', page).error('PATCH', /\/admin\/tenants\/.+/, 404, 'tenant_not_found')
    await mountView(AdminTenantsView, { path: '/admin/tenants' })
    await click('[data-test="toggle-Acme GmbH"]')
    expect(toasts.error()).toContain('This organization does not exist or you are no member.')
  })

  it('reports a failing list', async () => {
    new FakeApi().error('GET', '/admin/tenants', 500, 'internal_error')
    await mountView(AdminTenantsView, { path: '/admin/tenants' })
    expect(exists('[data-test=error]')).toBe(true)
  })
})
