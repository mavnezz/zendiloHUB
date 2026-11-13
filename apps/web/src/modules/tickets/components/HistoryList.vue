<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { formatDateTime } from '@/core/format'
import type { HistoryEntry } from '../api'
import { useDirectory } from '../directory'

/** Who changed what in the ticket and when. */
defineProps<{ entries: HistoryEntry[] }>()

const i18n = useI18n()
const t = i18n.t
const te = (key: string) => i18n.te(key)
const directory = useDirectory()

const ID_FIELDS = ['owner_id', 'responsible_id']

function value(field: string | null, raw: string | null): string {
  if (raw === null) {
    return '–'
  }
  if (field === 'state' && te(`tickets.states.${raw}`)) {
    return t(`tickets.states.${raw}`)
  }
  if (field === 'priority' && te(`tickets.priorities.${raw}`)) {
    return t(`tickets.priorities.${raw}`)
  }
  if (field === 'queue_id') {
    return directory.queueName(raw)
  }
  if (field && ID_FIELDS.includes(field)) {
    return directory.memberName(raw)
  }
  if (field === 'pending_until') {
    return formatDateTime(raw)
  }
  return raw
}

function describe(entry: HistoryEntry): string {
  if (entry.action === 'changed') {
    const name = te(`tickets.fields.${entry.field}`) ? t(`tickets.fields.${entry.field}`) : (entry.field ?? '')
    return t('tickets.history.changed', {
      field: name,
      old: value(entry.field, entry.old),
      new: value(entry.field, entry.new),
    })
  }
  if (entry.action === 'message') {
    return t(`tickets.history.message.${entry.new === 'internal' ? 'note' : 'public'}`)
  }
  return t(`tickets.history.${entry.action}`, { value: entry.new ?? '', kind: entry.field ?? '' })
}
</script>

<template>
  <ol class="grid gap-2 text-sm">
    <li v-for="entry in entries" :key="entry.id" class="flex flex-wrap gap-x-2" data-test="history-entry">
      <time class="text-xs text-muted-foreground" :datetime="entry.created_at">{{
        formatDateTime(entry.created_at)
      }}</time>
      <span class="font-medium">{{ entry.actor_name }}</span>
      <span>{{ describe(entry) }}</span>
    </li>
  </ol>
</template>
