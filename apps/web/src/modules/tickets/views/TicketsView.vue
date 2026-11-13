<script setup lang="ts">
import { Inbox, Plus, Search } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import Pager from '@/core/components/Pager.vue'
import { PAGE_SIZE } from '@/core/composables/use-page'
import { errorText } from '@/core/i18n/i18n'
import { cn } from '@/core/lib/utils'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { useSession } from '@/modules/identity/session'
import { useTenants } from '@/modules/tenancy/tenants'
import {
  PRIORITIES,
  SETTABLE_STATES,
  ticketsApi,
  VIEWS,
  type BulkRequest,
  type Priority,
  type TicketCounts,
  type TicketPage,
  type TicketView,
} from '../api'
import TicketTable from '../components/TicketTable.vue'
import { useDirectory } from '../directory'

/** The inbox: ready-made views with their counts, filters, search and changes for many tickets at once. */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const tenants = useTenants()
const session = useSession()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)

const view = computed<TicketView>(() => {
  const asked = String(route.query.view ?? 'open') as TicketView
  return VIEWS.includes(asked) ? asked : 'open'
})
const search = ref(String(route.query.q ?? ''))
const queueFilter = ref(String(route.query.queue ?? ''))
const priorityFilter = ref(String(route.query.priority ?? '') as Priority | '')
const offset = ref(0)

const page = ref<TicketPage | null>(null)
const counts = ref<TicketCounts | null>(null)
const error = ref<string | null>(null)
const selected = ref<string[]>([])

async function load(): Promise<void> {
  try {
    const [found, counted] = await Promise.all([
      ticketsApi.list(tenantId.value, {
        view: view.value,
        q: search.value.trim() || undefined,
        queue_id: queueFilter.value || undefined,
        priority: priorityFilter.value || undefined,
        offset: offset.value,
        limit: PAGE_SIZE,
      }),
      ticketsApi.counts(tenantId.value),
    ])
    page.value = found
    counts.value = counted
    error.value = null
    selected.value = selected.value.filter((id) => found.items.some((ticket) => ticket.id === id))
  } catch (caught) {
    error.value = errorText(caught)
  }
}

onMounted(async () => {
  await directory.load().catch(() => undefined)
  await load()
})

function applyFilters(): void {
  offset.value = 0
  void router.replace({
    query: {
      view: view.value,
      q: search.value.trim() || undefined,
      queue: queueFilter.value || undefined,
      priority: priorityFilter.value || undefined,
    },
  })
}

watch(
  () => route.query,
  () => void load(),
)
watch([queueFilter, priorityFilter], applyFilters)

function move(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  void load()
}

function count(each: TicketView): number | null {
  return counts.value && each in counts.value ? counts.value[each as keyof TicketCounts] : null
}

const queueOptions = computed(() => [
  { value: '', label: t('tickets.allQueues') },
  ...directory.queues.value.map((queue) => ({ value: queue.id, label: queue.name })),
])
const priorityOptions = computed(() => [
  { value: '' as const, label: t('tickets.anyPriority') },
  ...PRIORITIES.map((value) => ({ value, label: t(`tickets.priorities.${value}`) })),
])

/** Bulk changes: one field at a time, picked from a select. */
const bulkAction = ref('')
const bulkOptions = computed(() => [
  { value: '', label: t('tickets.bulk.choose') },
  { value: 'owner:me', label: t('tickets.bulk.takeAll') },
  { value: 'owner:none', label: t('tickets.bulk.unassign') },
  ...SETTABLE_STATES.filter((state) => !state.startsWith('pending')).map((state) => ({
    value: `state:${state}`,
    label: t('tickets.bulk.state', { state: t(`tickets.states.${state}`) }),
  })),
  ...PRIORITIES.map((priority) => ({
    value: `priority:${priority}`,
    label: t('tickets.bulk.priority', { priority: t(`tickets.priorities.${priority}`) }),
  })),
  ...directory.queues.value.map((queue) => ({
    value: `queue:${queue.id}`,
    label: t('tickets.bulk.queue', { queue: queue.name }),
  })),
])

async function applyBulk(): Promise<void> {
  const [field, value] = bulkAction.value.split(':') as [string, string]
  const body: BulkRequest = { ticket_ids: selected.value }
  if (field === 'owner') {
    body.owner_id = value === 'me' ? (session.user.value?.id ?? null) : null
  } else if (field === 'state') {
    body.state = value as BulkRequest['state']
  } else if (field === 'priority') {
    body.priority = value as Priority
  } else {
    body.queue_id = value
  }
  try {
    const result = await ticketsApi.bulk(tenantId.value, body)
    const failed = Object.keys(result.failed).length
    if (failed) {
      notify.error(t('tickets.bulk.partly', { changed: result.changed.length, failed }))
    } else {
      notify.success(t('tickets.bulk.done', { count: result.changed.length }))
    }
  } catch (caught) {
    notify.error(caught)
  }
  bulkAction.value = ''
  selected.value = []
  await load()
}
</script>

<template>
  <div class="mx-auto grid max-w-7xl gap-6">
    <PageHeader :title="$t('tickets.title')" :description="$t('tickets.description')">
      <Button v-if="directory.creatable.value.length" as-child data-test="new-ticket">
        <RouterLink :to="{ name: 'newTicket', params: { tenantId } }"
          ><Plus class="size-4" /> {{ $t('tickets.new') }}</RouterLink
        >
      </Button>
    </PageHeader>

    <div class="grid gap-6 lg:grid-cols-[14rem_1fr]">
      <nav class="flex gap-1 overflow-x-auto lg:flex-col" :aria-label="$t('tickets.views.label')">
        <RouterLink
          v-for="each in VIEWS"
          :key="each"
          :to="{ query: { ...route.query, view: each } }"
          :class="
            cn(
              'flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm whitespace-nowrap hover:bg-muted',
              each === view && 'bg-muted font-medium',
            )
          "
          :data-test="`view-${each}`"
          @click="offset = 0"
        >
          <span>{{ $t(`tickets.views.${each}`) }}</span>
          <span v-if="count(each) !== null" class="text-xs text-muted-foreground" :data-test="`count-${each}`">{{
            count(each)
          }}</span>
        </RouterLink>
      </nav>

      <div class="grid min-w-0 gap-4">
        <div class="flex flex-wrap items-center gap-2">
          <form class="relative min-w-56 flex-1" @submit.prevent="applyFilters">
            <Search class="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
            <Input
              v-model="search"
              type="search"
              class="pl-8"
              :placeholder="$t('tickets.searchPlaceholder')"
              data-test="search"
            />
          </form>
          <NativeSelect v-model="queueFilter" :options="queueOptions" class="w-44" :aria-label="$t('tickets.queue')" />
          <NativeSelect
            v-model="priorityFilter"
            :options="priorityOptions"
            class="w-40"
            :aria-label="$t('tickets.priority')"
          />
        </div>

        <div
          v-if="selected.length"
          class="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 p-2 text-sm"
          data-test="bulk"
        >
          <span class="px-1">{{ $t('tickets.bulk.selected', { count: selected.length }) }}</span>
          <NativeSelect
            v-model="bulkAction"
            :options="bulkOptions"
            class="w-64"
            :aria-label="$t('tickets.bulk.choose')"
          />
          <Button size="sm" :disabled="!bulkAction" data-test="bulk-apply" @click="applyBulk">{{
            $t('tickets.bulk.apply')
          }}</Button>
        </div>

        <ErrorAlert v-if="error" :message="error" />
        <EmptyState
          v-else-if="page && page.items.length === 0"
          :title="$t('tickets.empty')"
          :description="$t(`tickets.emptyHints.${view}`)"
        >
          <template #icon><Inbox class="size-8 text-muted-foreground" /></template>
        </EmptyState>
        <Card v-else-if="page">
          <CardContent class="overflow-x-auto">
            <TicketTable v-model:selected="selected" :tickets="page.items" selectable />
            <Pager
              :label="$t('tickets.count', { count: page.total })"
              :has-previous="offset > 0"
              :has-next="offset + PAGE_SIZE < page.total"
              @move="move"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
