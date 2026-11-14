<script setup lang="ts">
import { ArrowDown, ArrowUp, Pencil, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import type { Queue } from '@/modules/access/api'
import type { MailFilter } from '../api'

/** The filters of one scope (all mailboxes, or one mailbox's rules) in the order they run, to edit and reorder. */
const props = defineProps<{
  filters: MailFilter[]
  queues: Queue[]
  /** Numbers the rules (1., 2., …) as steps of the mailbox's way. */
  numbered?: boolean
}>()
const emit = defineEmits<{
  edit: [found: MailFilter]
  delete: [found: MailFilter]
  /** The ids in their new order. */
  reorder: [ids: string[]]
}>()

const { t } = useI18n()

function move(index: number, delta: number): void {
  const ids = props.filters.map((each) => each.id)
  const [moved] = ids.splice(index, 1)
  ids.splice(index + delta, 0, moved!)
  emit('reorder', ids)
}

function conditions(found: MailFilter): string {
  return found.conditions
    .map(
      (each) =>
        `${each.field === 'header' ? each.header : t(`channels.filters.fields.${each.field}`)} ${t(`channels.filters.operators.${each.operator}`)} „${each.value}“`,
    )
    .join(found.match === 'all' ? ` ${t('channels.filters.and')} ` : ` ${t('channels.filters.or')} `)
}

function actions(found: MailFilter): string {
  const chosen = found.actions
  if (chosen.ignore) {
    return t('channels.filters.dropped')
  }
  const parts = []
  if (chosen.queue_id) {
    const name = props.queues.find((queue) => queue.id === chosen.queue_id)?.name ?? '?'
    parts.push(t('channels.filters.toQueue', { queue: name }))
  }
  if (chosen.priority) {
    parts.push(t('tickets.bulk.priority', { priority: t(`tickets.priorities.${chosen.priority}`) }))
  }
  const tags = chosen.tags ?? []
  if (tags.length) {
    parts.push(tags.map((tag) => `#${tag}`).join(' '))
  }
  return parts.join(' · ')
}
</script>

<template>
  <div class="grid gap-2">
    <div
      v-for="(found, index) in filters"
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
          :disabled="index === filters.length - 1"
          :aria-label="$t('channels.filters.down')"
          :data-test="`down-${found.name}`"
          @click="move(index, 1)"
          ><ArrowDown class="size-3.5"
        /></Button>
      </span>
      <div class="min-w-0 flex-1">
        <p class="flex items-center gap-2 font-medium">
          <span v-if="numbered" class="text-muted-foreground">{{ index + 1 }}.</span>
          {{ found.name }}
          <Badge v-if="!found.active" variant="outline">{{ $t('channels.filters.inactive') }}</Badge>
          <Badge v-if="found.stop" variant="outline">{{ $t('channels.filters.stops') }}</Badge>
        </p>
        <p class="truncate text-xs text-muted-foreground">{{ conditions(found) }} → {{ actions(found) }}</p>
      </div>
      <Button
        variant="ghost"
        size="icon"
        :aria-label="$t('common.edit')"
        :data-test="`edit-${found.name}`"
        @click="emit('edit', found)"
        ><Pencil class="size-4"
      /></Button>
      <Button
        variant="ghost"
        size="icon"
        :aria-label="$t('common.delete')"
        :data-test="`delete-${found.name}`"
        @click="emit('delete', found)"
        ><Trash2 class="size-4"
      /></Button>
    </div>
  </div>
</template>
