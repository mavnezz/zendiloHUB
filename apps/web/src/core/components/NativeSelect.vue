<script setup lang="ts" generic="T extends string">
import { ChevronDown } from '@lucide/vue'
import { cn } from '@/core/lib/utils'

/** A styled native select: fine for long lists (time zones) and works the same everywhere. */
defineProps<{
  options: readonly { value: T; label: string }[]
  id?: string
  disabled?: boolean
  class?: string
  ariaLabel?: string
}>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div :class="cn('relative', $props.class)">
    <select
      :id="id"
      v-model="model"
      :disabled="disabled"
      :aria-label="ariaLabel"
      class="h-9 w-full appearance-none rounded-md border border-input bg-transparent py-1 pr-8 pl-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30"
    >
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
    <ChevronDown class="pointer-events-none absolute top-2.5 right-2.5 size-4 text-muted-foreground" />
  </div>
</template>
