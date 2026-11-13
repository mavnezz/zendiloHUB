<script setup lang="ts">
import { CircleCheck, CircleX } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { formatDateTime } from '@/core/format'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import type { AuditEntry } from '../api'

defineProps<{ entries: readonly AuditEntry[] }>()

const i18n = useI18n()

/** Known actions in words, unknown ones (from newer modules) as their stable name. */
function actionText(action: string): string {
  const key = `audit.actions.${action}`
  return i18n.te(key) ? i18n.t(key) : action
}
</script>

<template>
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>{{ $t('audit.time') }}</TableHead>
        <TableHead>{{ $t('audit.actor') }}</TableHead>
        <TableHead>{{ $t('audit.action') }}</TableHead>
        <TableHead class="hidden md:table-cell">{{ $t('audit.target') }}</TableHead>
        <TableHead>{{ $t('audit.result') }}</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      <TableRow v-for="entry in entries" :key="entry.id" data-test="entry">
        <TableCell class="whitespace-nowrap text-muted-foreground">{{ formatDateTime(entry.created_at) }}</TableCell>
        <TableCell>
          <span v-if="entry.actor_email">{{ entry.actor_email }}</span>
          <span v-else class="text-muted-foreground italic">{{ $t('audit.unknownActor') }}</span>
        </TableCell>
        <TableCell data-test="action">{{ actionText(entry.action) }}</TableCell>
        <TableCell class="hidden max-w-xs truncate text-muted-foreground md:table-cell">{{ entry.target }}</TableCell>
        <TableCell>
          <span v-if="entry.succeeded" class="inline-flex items-center gap-1 text-sm" data-test="succeeded">
            <CircleCheck class="size-4 text-status-good" /> {{ $t('audit.succeeded') }}
          </span>
          <span v-else class="inline-flex items-center gap-1 text-sm" data-test="failed">
            <CircleX class="size-4 text-destructive" /> {{ $t('audit.failed', { status: entry.status }) }}
          </span>
        </TableCell>
      </TableRow>
      <TableRow v-if="!entries.length">
        <TableCell colspan="5" class="py-8 text-center text-muted-foreground">{{ $t('audit.empty') }}</TableCell>
      </TableRow>
    </TableBody>
  </Table>
</template>
