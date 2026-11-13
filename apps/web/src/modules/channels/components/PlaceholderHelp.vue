<script setup lang="ts">
/** The placeholders a text may use; clicking one inserts it. */
defineProps<{ placeholders: readonly string[] }>()
defineEmits<{ insert: [placeholder: string] }>()

const wrap = (placeholder: string) => ['{', '{', placeholder, '}', '}'].join('')
</script>

<template>
  <div class="flex flex-wrap gap-1" data-test="placeholders">
    <button
      v-for="placeholder in placeholders"
      :key="placeholder"
      type="button"
      class="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-xs hover:bg-muted"
      :data-test="`placeholder-${placeholder}`"
      @click="$emit('insert', wrap(placeholder))"
      v-text="wrap(placeholder)"
    />
  </div>
</template>
