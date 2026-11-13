<script setup lang="ts">
import { ArrowDown, ArrowUp, Filter, Pencil, Plus, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { accessApi } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi, type FilterRequest, type MailFilter } from '../api'
import FilterDialog from '../components/FilterDialog.vue'

/** Rules for incoming mail, run from top to bottom (like OTOBO's postmaster filters). */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const filters = useAsyncData(() => channelsApi.filters(tenantId.value))
const queues = useAsyncData(() => accessApi.queues(tenantId.value))

const editing = ref<MailFilter | null>(null)
const dialogOpen = ref(false)
const deleting = ref<MailFilter | null>(null)
const deleteOpen = ref(false)

function openDialog(found: MailFilter | null): void {
  editing.value = found
  dialogOpen.value = true
}

async function save(body: FilterRequest): Promise<void> {
  const saved = editing.value
    ? await channelsApi.updateFilter(tenantId.value, editing.value.id, body)
    : await channelsApi.createFilter(tenantId.value, body)
  notify.success(t('channels.filters.saved', { name: saved.name }))
  await filters.reload()
}

async function move(index: number, delta: number): Promise<void> {
  const ids = (filters.data.value ?? []).map((each) => each.id)
  const [moved] = ids.splice(index, 1)
  ids.splice(index + delta, 0, moved!)
  try {
    filters.data.value = await channelsApi.reorderFilters(tenantId.value, ids)
  } catch (caught) {
    notify.error(caught)
  }
}

function describe(found: MailFilter): string {
  const actions = found.actions
  if (actions.ignore) {
    return t('channels.filters.dropped')
  }
  const parts = []
  if (actions.queue_id) {
    const name = queues.data.value?.find((queue) => queue.id === actions.queue_id)?.name ?? '?'
    parts.push(t('channels.filters.toQueue', { queue: name }))
  }
  if (actions.priority) {
    parts.push(t('tickets.bulk.priority', { priority: t(`tickets.priorities.${actions.priority}`) }))
  }
  const tags = actions.tags ?? []
  if (tags.length) {
    parts.push(tags.map((tag) => `#${tag}`).join(' '))
  }
  return parts.join(' · ')
}

function askDelete(found: MailFilter): void {
  deleting.value = found
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const found = deleting.value!
  await channelsApi.deleteFilter(tenantId.value, found.id)
  notify.success(t('channels.filters.deleted', { name: found.name }))
  await filters.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('channels.filters.title')" :description="$t('channels.filters.description')">
      <Button data-test="create-filter" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('channels.filters.create') }}</Button
      >
    </PageHeader>
    <ErrorAlert v-if="filters.error.value" :message="filters.error.value" />
    <EmptyState
      v-else-if="filters.data.value?.length === 0"
      :title="$t('channels.filters.empty')"
      :description="$t('channels.filters.emptyHint')"
    >
      <template #icon><Filter class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="filters.data.value">
      <CardContent class="grid gap-2 pt-6">
        <div
          v-for="(found, index) in filters.data.value"
          :key="found.id"
          class="flex items-center gap-3 rounded-md border p-3"
          :data-test="`filter-${found.name}`"
        >
          <span class="flex flex-col">
            <Button
              variant="ghost"
              size="icon"
              class="size-6"
              :disabled="index === 0"
              :aria-label="$t('channels.filters.up')"
              :data-test="`up-${found.name}`"
              @click="move(index, -1)"
              ><ArrowUp class="size-3.5"
            /></Button>
            <Button
              variant="ghost"
              size="icon"
              class="size-6"
              :disabled="index === filters.data.value.length - 1"
              :aria-label="$t('channels.filters.down')"
              @click="move(index, 1)"
              ><ArrowDown class="size-3.5"
            /></Button>
          </span>
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-2 font-medium">
              {{ found.name }}
              <Badge v-if="!found.active" variant="outline">{{ $t('channels.filters.inactive') }}</Badge>
              <Badge v-if="found.stop" variant="outline">{{ $t('channels.filters.stops') }}</Badge>
            </p>
            <p class="truncate text-xs text-muted-foreground">
              {{
                found.conditions
                  .map(
                    (each) =>
                      `${each.field === 'header' ? each.header : $t(`channels.filters.fields.${each.field}`)} ${$t(`channels.filters.operators.${each.operator}`)} „${each.value}“`,
                  )
                  .join(found.match === 'all' ? ` ${$t('channels.filters.and')} ` : ` ${$t('channels.filters.or')} `)
              }}
              → {{ describe(found) }}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.edit')"
            :data-test="`edit-${found.name}`"
            @click="openDialog(found)"
            ><Pencil class="size-4"
          /></Button>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.delete')"
            :data-test="`delete-${found.name}`"
            @click="askDelete(found)"
            ><Trash2 class="size-4"
          /></Button>
        </div>
      </CardContent>
    </Card>
    <FilterDialog v-model:open="dialogOpen" :initial="editing" :queues="queues.data.value ?? []" :save="save" />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('channels.filters.deleteTitle', { name: deleting?.name })"
      :description="$t('channels.filters.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
