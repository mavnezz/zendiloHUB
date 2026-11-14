<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatDate } from '@/core/format'
import type { Report } from '../api'

/**
 * Tickets opened and closed per day as grouped bars (two series: legend always shown). Colors are slots 1 and 2 of
 * the validated default categorical palette (blue, orange), stepped for dark mode (the app's `.dark` class); hovering a day shows its values.
 */
const props = defineProps<{ days: Report['days'] }>()

const HEIGHT = 160
const hovered = ref<number | null>(null)
const max = computed(() => Math.max(1, ...props.days.flatMap((day) => [day.created, day.closed])))
const width = computed(() => Math.max(props.days.length * 24, 240))
const slot = computed(() => width.value / Math.max(props.days.length, 1))
const bar = computed(() => Math.max(2, Math.min(10, (slot.value - 6) / 2)))
const ticks = computed(() => {
  const top = max.value
  return [0, Math.round(top / 2), top].filter((value, index, all) => all.indexOf(value) === index)
})
const labelEvery = computed(() => Math.ceil(props.days.length / 8))

function y(value: number): number {
  return HEIGHT - (value / max.value) * HEIGHT
}

/** A bar with 4px rounded top corners, sitting square on the baseline. */
function path(x: number, value: number): string {
  if (value === 0) {
    return ''
  }
  const top = y(value)
  const r = Math.min(4, bar.value / 2, HEIGHT - top)
  const w = bar.value
  return `M${x},${HEIGHT} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} Q${x + w},${top} ${x + w},${top + r} V${HEIGHT} Z`
}
</script>

<template>
  <div class="viz-root grid gap-2" data-test="daily-chart">
    <div class="flex gap-4 text-xs text-muted-foreground" data-test="legend">
      <span class="flex items-center gap-1.5"
        ><span class="size-2.5 rounded-sm" style="background: var(--series-1)" />{{ $t('reports.opened') }}</span
      >
      <span class="flex items-center gap-1.5"
        ><span class="size-2.5 rounded-sm" style="background: var(--series-2)" />{{ $t('reports.closed') }}</span
      >
    </div>
    <div class="relative overflow-x-auto">
      <svg
        :viewBox="`-28 -8 ${width + 36} ${HEIGHT + 28}`"
        :width="width + 36"
        :height="HEIGHT + 28"
        role="img"
        :aria-label="$t('reports.chartLabel')"
      >
        <g v-for="tick in ticks" :key="tick">
          <line x1="0" :x2="width" :y1="y(tick)" :y2="y(tick)" class="stroke-border" stroke-width="1" />
          <text x="-6" :y="y(tick) + 3" text-anchor="end" class="fill-muted-foreground text-[10px]">{{ tick }}</text>
        </g>
        <g
          v-for="(day, index) in days"
          :key="day.day"
          :data-test="`day-${day.day}`"
          @mouseenter="hovered = index"
          @mouseleave="hovered = null"
        >
          <rect :x="index * slot" y="-8" :width="slot" :height="HEIGHT + 8" fill="transparent" />
          <path :d="path(index * slot + slot / 2 - bar - 1, day.created)" style="fill: var(--series-1)" />
          <path :d="path(index * slot + slot / 2 + 1, day.closed)" style="fill: var(--series-2)" />
          <text
            v-if="index % labelEvery === 0"
            :x="index * slot + slot / 2"
            :y="HEIGHT + 16"
            text-anchor="middle"
            class="fill-muted-foreground text-[10px]"
          >
            {{ day.day.slice(5) }}
          </text>
        </g>
      </svg>
      <div
        v-if="hovered !== null && days[hovered]"
        class="pointer-events-none absolute top-0 rounded-md border bg-popover px-2 py-1 text-xs shadow-sm"
        :style="{ left: `${Math.min(hovered * slot + 28, width - 80)}px` }"
        data-test="chart-tooltip"
      >
        <p class="font-medium">{{ formatDate(days[hovered]!.day) }}</p>
        <p>{{ $t('reports.opened') }}: {{ days[hovered]!.created }}</p>
        <p>{{ $t('reports.closed') }}: {{ days[hovered]!.closed }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.viz-root {
  --series-1: #2a78d6;
  --series-2: #eb6834;
}
:global(.dark) .viz-root {
  --series-1: #3987e5;
  --series-2: #d95926;
}
</style>
