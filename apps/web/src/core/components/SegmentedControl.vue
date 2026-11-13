<script setup lang="ts" generic="T extends string | number">
import { cn } from '@/core/lib/utils'

/** A row of buttons for a few options, one of them chosen (like a radio group). */
defineProps<{ options: readonly { value: T; label: string }[]; label: string; disabled?: boolean }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div role="radiogroup" :aria-label="label" class="inline-flex flex-wrap rounded-md border bg-muted/40 p-0.5">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      :aria-checked="model === option.value"
      :disabled="disabled"
      :data-test="`option-${option.value}`"
      :class="
        cn(
          'rounded px-3 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50',
          model === option.value && 'bg-background font-medium text-foreground shadow-sm',
        )
      "
      @click="model = option.value"
    >
      {{ option.label }}
    </button>
  </div>
</template>
