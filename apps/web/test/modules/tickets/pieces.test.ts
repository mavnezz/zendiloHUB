import { describe, expect, it } from 'vitest'
import { roleLabel } from '@/modules/tenancy/roles'
import { useTenants } from '@/modules/tenancy/tenants'
import { fromLocalInput, ticketsApi, toLocalInput, type HistoryEntry } from '@/modules/tickets/api'
import HistoryList from '@/modules/tickets/components/HistoryList.vue'
import { useDirectory } from '@/modules/tickets/directory'
import { FakeApi } from '../../support/fake-api'
import { member, role, tenant, TENANT_ID } from '../../support/fixtures'
import { queue } from '../../support/helpdesk'
import { $$, mountView } from '../../support/mount'

const BASE = `/tenants/${TENANT_ID}`

function entry(overrides: Partial<HistoryEntry>): HistoryEntry {
  return {
    id: crypto.randomUUID(),
    actor_id: 'u1',
    actor_name: 'ada@example.org',
    action: 'changed',
    field: null,
    old: null,
    new: null,
    created_at: '2026-11-13T12:00:00Z',
    ...overrides,
  }
}

describe('ticket helpers', () => {
  it('converts dates for datetime inputs', () => {
    expect(fromLocalInput('')).toBeNull()
    expect(fromLocalInput('nonsense')).toBeNull()
    expect(fromLocalInput('2026-11-20T09:00')).toBe(new Date('2026-11-20T09:00').toISOString())
    expect(toLocalInput(null)).toBe('')
    expect(toLocalInput(new Date('2026-11-20T09:05').toISOString())).toBe('2026-11-20T09:05')
  })

  it('calls the remaining ticket routes', async () => {
    const fake = new FakeApi()
      .json('GET', `${BASE}/tickets/by-number/1001`, { id: 't1' })
      .json('GET', `${BASE}/tickets/t1/time`, [])
      .json('POST', `${BASE}/tickets/t1/time`, { id: 'e1' }, 201)
      .on('DELETE', `${BASE}/tickets/t1/watch`, { status: 204 })
    await ticketsApi.byNumber(TENANT_ID, 1001)
    await ticketsApi.time(TENANT_ID, 't1')
    await ticketsApi.recordTime(TENANT_ID, 't1', 15)
    await ticketsApi.unwatch(TENANT_ID, 't1')
    expect(fake.last('POST', `${BASE}/tickets/t1/time`)?.body).toEqual({ minutes: 15 })
    expect(fake.calls('DELETE', `${BASE}/tickets/t1/watch`)).toHaveLength(1)
  })

  it('names roles, queues and members it does not know', () => {
    expect(roleLabel('agent')).toBe('Agent')
    expect(roleLabel('r1', [role()])).toBe('Team lead')
    expect(roleLabel('r9', [], 'Seer')).toBe('Seer')
    expect(roleLabel('r9')).toBe('Own role')
    const directory = useDirectory()
    expect(directory.queueName('q9')).toBe('Unknown queue')
    expect(directory.memberName(null)).toBe('Nobody')
  })
})

describe('HistoryList', () => {
  it('describes every kind of change', async () => {
    useTenants().put(tenant())
    useTenants().select(TENANT_ID)
    new FakeApi().json('GET', `${BASE}/queues`, [queue()]).json('GET', `${BASE}/members`, [member()])
    await useDirectory().load()
    await mountView(HistoryList, {
      props: {
        entries: [
          entry({ field: 'priority', old: 'normal', new: 'urgent' }),
          entry({ field: 'queue_id', old: 'q1', new: 'q9' }),
          entry({ field: 'responsible_id', old: 'u1', new: null }),
          entry({ field: 'pending_until', old: null, new: '2026-11-20T09:00:00Z' }),
          entry({ field: 'state', old: 'weird', new: 'closed' }),
          entry({ field: 'tags', old: 'a', new: 'a, b' }),
          entry({ field: 'mystery', old: 'x', new: 'y' }),
          entry({ action: 'message', new: 'internal' }),
          entry({ action: 'message', new: 'public' }),
          entry({ action: 'linked', field: 'parent', new: '1002' }),
          entry({ action: 'time', new: '15' }),
        ],
      },
    })
    expect($$('[data-test=history-entry]').map((each) => each.text().replace(/^.*?ada@example\.org/, ''))).toEqual([
      'changed the priority from Normal to Urgent',
      'changed the queue from Support to Unknown queue',
      'changed the responsible from ada@example.org to –',
      expect.stringMatching(/^changed the waiting until from – to Nov 20, 2026/),
      'changed the state from weird to Closed',
      'changed the tags from a to a, b',
      'changed the mystery from x to y',
      'added an internal note',
      'added a message',
      'linked #1002 (parent)',
      'recorded 15 minutes',
    ])
  })
})
