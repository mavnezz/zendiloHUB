<script setup lang="ts">
import { ArrowDown, ArrowUp, ChevronsUp, Minus } from '@lucide/vue'
import { computed } from 'vue'
import { cn } from '@/core/lib/utils'
import type { Priority } from '../api'

const props = defineProps<{ priority: Priority }>()

const LOOK = {
  low: { icon: ArrowDown, color: 'text-muted-foreground' },
  normal: { icon: Minus, color: 'text-muted-foreground' },
  high: { icon: ArrowUp, color: 'text-orange-600 dark:text-orange-400' },
  urgent: { icon: ChevronsUp, color: 'text-red-600 dark:text-red-400' },
} as const
const look = computed(() => LOOK[props.priority])
</script>

<template>
  <span :class="cn('inline-flex items-center gap-1 text-xs whitespace-nowrap', look.color)">
    <component :is="look.icon" class="size-3.5" />{{ $t(`tickets.priorities.${priority}`) }}
  </span>
</template>
