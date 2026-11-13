import { describe, expect, it } from 'vitest'
import type { Grant, Group, Queue, RightsMatrix } from '@/modules/access/api'
import GroupsView from '@/modules/access/views/GroupsView.vue'
import QueueRightsView from '@/modules/access/views/QueueRightsView.vue'
import QueuesView from '@/modules/access/views/QueuesView.vue'
import { useTenants } from '@/modules/tenancy/tenants'
import { FakeApi } from '../../support/fake-api'
import { member, tenant, TENANT_ID } from '../../support/fixtures'
import { $, $$, click, exists, flushPromises, mountView, text, type } from '../../support/mount'
import { spyToasts } from '../../support/toasts'

const BASE = `/tenants/${TENANT_ID}`
const FULL = ['view', 'create', 'note', 'reply', 'edit', 'assign', 'move'] as const

function inTenant(): void {
  const tenants = useTenants()
  tenants.put(tenant())
  tenants.select(TENANT_ID)
}

function queue(overrides: Partial<Queue> = {}): Queue {
  return {
    id: 'q1',
    name: 'Support',
    description: 'First contact',
    created_at: '2026-11-13T12:00:00Z',
    rights: [...FULL],
    ...overrides,
  }
}

function group(overrides: Partial<Group> = {}): Group {
  return {
    id: 'g1',
    name: '1st level',
    description: '',
    member_ids: [],
    created_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

function matrix(grants: Grant[] = []): RightsMatrix {
  return {
    rights: [...FULL],
    presets: {
      read: ['view'],
      contribute: ['view', 'note'],
      work: ['view', 'create', 'note', 'reply', 'edit'],
      full: [...FULL],
    },
    grants,
  }
}

describe('QueuesView', () => {
  it('creates, renames and deletes queues', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = new FakeApi()
      .json('GET', `${BASE}/queues`, [queue()])
      .json('POST', `${BASE}/queues`, queue({ id: 'q2', name: 'Billing' }), 201)
      .json('PATCH', `${BASE}/queues/q1`, queue({ name: 'Helpdesk' }))
      .on('DELETE', `${BASE}/queues/q1`, { status: 204 })
    await mountView(QueuesView, { path: `/t/${TENANT_ID}/queues` })
    expect($$('[data-test=queue]').map((row) => row.text())).toEqual([expect.stringContaining('First contact')])

    await click('[data-test=create-queue]')
    await type('#access-name', 'Billing')
    await type('#access-description', 'Invoices')
    await click('[data-test=save]')
    expect(fake.last('POST', `${BASE}/queues`)?.body).toEqual({ name: 'Billing', description: 'Invoices' })
    expect(toasts.success()).toContain('Queue "Billing" created')

    await click('[data-test=edit-queue-q1]')
    expect(($('#access-name').element as HTMLInputElement).value).toBe('Support')
    await type('#access-name', 'Helpdesk')
    await click('[data-test=save]')
    expect(fake.last('PATCH', `${BASE}/queues/q1`)?.body).toEqual({ name: 'Helpdesk', description: 'First contact' })

    await click('[data-test=delete-queue-q1]')
    expect(text()).toContain('Delete the queue "Support"?')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/queues/q1`)).toHaveLength(1)
    expect(fake.calls('GET', `${BASE}/queues`)).toHaveLength(4)
  })

  it('shows what the server refuses and an empty list', async () => {
    inTenant()
    new FakeApi().json('GET', `${BASE}/queues`, []).error('POST', `${BASE}/queues`, 409, 'queue_name_taken')
    await mountView(QueuesView, { path: `/t/${TENANT_ID}/queues` })
    expect(text()).toContain('No queues yet')
    await click('[data-test=create-queue]')
    await type('#access-name', 'Support')
    await click('[data-test=save]')
    expect($('[data-test=error]').text()).toContain('There is already a queue of this name.')
  })

  it('reports a failing list', async () => {
    inTenant()
    new FakeApi().error('GET', `${BASE}/queues`, 500, 'internal_error')
    await mountView(QueuesView, { path: `/t/${TENANT_ID}/queues` })
    expect(exists('[data-test=error]')).toBe(true)
  })
})

describe('GroupsView', () => {
  it('creates groups and picks their members', async () => {
    inTenant()
    const toasts = spyToasts()
    const members = [member(), member({ user_id: 'u2', email: 'bob@example.org', role: 'agent' })]
    const fake = new FakeApi()
      .json('GET', `${BASE}/groups`, [group({ member_ids: ['u1'] })])
      .json('GET', `${BASE}/members`, members)
      .json('POST', `${BASE}/groups`, group({ id: 'g2', name: 'Tech' }), 201)
      .json('PUT', `${BASE}/groups/g1/members`, group({ member_ids: ['u2'] }))
      .json('PATCH', `${BASE}/groups/g1`, group({ name: 'First level' }))
      .on('DELETE', `${BASE}/groups/g1`, { status: 204 })
    await mountView(GroupsView, { path: `/t/${TENANT_ID}/groups` })
    expect($('[data-test=members-g1]').text()).toBe('ada@example.org')

    await click('[data-test=create-group]')
    await type('#access-name', 'Tech')
    await click('[data-test=save]')
    expect(fake.last('POST', `${BASE}/groups`)?.body).toEqual({ name: 'Tech', description: '' })
    expect(toasts.success()).toContain('Group "Tech" created')

    await click('[data-test=edit-members-g1]')
    expect(text()).toContain('Members of 1st level')
    await click('[data-test="member-ada@example.org"] button')
    await click('[data-test="member-bob@example.org"] button')
    await click('[data-test=save-members]')
    expect(fake.last('PUT', `${BASE}/groups/g1/members`)?.body).toEqual({ user_ids: ['u2'] })
    expect(toasts.success()).toContain('Members of "1st level" saved')

    await click('[data-test=edit-group-g1]')
    await type('#access-name', 'First level')
    await click('[data-test=save]')
    expect(fake.last('PATCH', `${BASE}/groups/g1`)?.body).toEqual({ name: 'First level', description: '' })

    await click('[data-test=delete-group-g1]')
    await click('[data-test=confirm]')
    expect(fake.calls('DELETE', `${BASE}/groups/g1`)).toHaveLength(1)
  })

  it('reports members the server refuses, and an empty list', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/groups`, [group()])
      .json('GET', `${BASE}/members`, [member()])
      .error('PUT', `${BASE}/groups/g1/members`, 422, 'not_a_member')
    await mountView(GroupsView, { path: `/t/${TENANT_ID}/groups` })
    expect($('[data-test=members-g1]').text()).toBe('Nobody yet')
    await click('[data-test=edit-members-g1]')
    await click('[data-test=save-members]')
    expect($('[data-test=error]').text()).toContain('Only members of the organization')

    new FakeApi().json('GET', `${BASE}/groups`, []).json('GET', `${BASE}/members`, [])
    await mountView(GroupsView, { path: `/t/${TENANT_ID}/groups` })
    expect(text()).toContain('No groups yet')
  })
})

describe('QueueRightsView', () => {
  function api(grants: Grant[] = []): FakeApi {
    return new FakeApi()
      .json('GET', `${BASE}/queues`, [queue(), queue({ id: 'q2', name: 'Billing' })])
      .json('GET', `${BASE}/groups`, [group(), group({ id: 'g2', name: 'Tech' })])
      .json('GET', `${BASE}/queue-rights`, matrix(grants))
      .on('PUT', `${BASE}/queue-rights`, (request) => ({ body: request.body }))
  }

  it('shows the level of each group in each queue and changes it', async () => {
    inTenant()
    const toasts = spyToasts()
    const fake = api([
      { group_id: 'g1', queue_id: 'q1', rights: ['view', 'note'], preset: 'contribute' },
      { group_id: 'g2', queue_id: 'q1', rights: ['view', 'move'], preset: null },
    ])
    await mountView(QueueRightsView, { path: `/t/${TENANT_ID}/queue-rights` })
    const cell = (groupId: string, queueId: string) =>
      $(`[data-test=cell-${groupId}-${queueId}] select`).element as HTMLSelectElement
    expect([cell('g1', 'q1').value, cell('g2', 'q1').value, cell('g1', 'q2').value]).toEqual([
      'contribute',
      'custom',
      'none',
    ])
    expect($('[data-test=custom-g2-q1]').text()).toBe('See, Move out')
    expect($('[data-test=legend]').text()).toContain('Work: See, Create, Internal notes, Reply, Edit')

    await $(`[data-test=cell-g1-q2] select`).setValue('work')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-rights`)?.body).toEqual({
      group_id: 'g1',
      queue_id: 'q2',
      rights: ['view', 'create', 'note', 'reply', 'edit'],
    })
    expect(toasts.success()).toContain('Rights of 1st level in Billing saved')

    await $(`[data-test=cell-g1-q1] select`).setValue('none')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-rights`)?.body).toMatchObject({ queue_id: 'q1', rights: [] })
  })

  it('picks custom rights one by one', async () => {
    inTenant()
    const fake = api([{ group_id: 'g2', queue_id: 'q1', rights: ['view'], preset: 'read' }])
    await mountView(QueueRightsView, { path: `/t/${TENANT_ID}/queue-rights` })

    await $(`[data-test=cell-g2-q1] select`).setValue('custom')
    expect(text()).toContain('Tech in Support')
    await click('[data-test=right-reply] button')
    await click('[data-test=save-rights]')
    await flushPromises()
    expect(fake.last('PUT', `${BASE}/queue-rights`)?.body).toEqual({
      group_id: 'g2',
      queue_id: 'q1',
      rights: ['view', 'reply'],
    })
  })

  it('asks for queues and groups first, and reports failures', async () => {
    inTenant()
    new FakeApi()
      .json('GET', `${BASE}/queues`, [])
      .json('GET', `${BASE}/groups`, [group()])
      .json('GET', `${BASE}/queue-rights`, matrix())
    await mountView(QueueRightsView, { path: `/t/${TENANT_ID}/queue-rights` })
    expect(text()).toContain('Queues and groups first')

    const toasts = spyToasts()
    new FakeApi().error('GET', `${BASE}/queues`, 500, 'internal_error')
    await mountView(QueueRightsView, { path: `/t/${TENANT_ID}/queue-rights` })
    expect(exists('[data-test=error]')).toBe(true)
    expect(toasts.error()).toHaveLength(1)

    api().error('PUT', `${BASE}/queue-rights`, 404, 'queue_not_found')
    await mountView(QueueRightsView, { path: `/t/${TENANT_ID}/queue-rights` })
    await $(`[data-test=cell-g1-q1] select`).setValue('read')
    await flushPromises()
    expect(toasts.error()).toContain('The queue does not exist.')
  })
})
