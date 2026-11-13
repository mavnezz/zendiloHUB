<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/core/lib/utils'
import type { TicketState } from '../api'

const props = defineProps<{ state: TicketState }>()

const COLORS: Record<TicketState, string> = {
  new: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  open: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  pending_reminder: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  pending_close: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  closed: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  merged: 'bg-muted text-muted-foreground',
}
const color = computed(() => COLORS[props.state])
</script>

<template>
  <span
    :class="cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap', color)"
    :data-test="`state-${state}`"
    >{{ $t(`tickets.states.${state}`) }}</span
  >
</template>
