<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center">
    <slot name="icon" />
    <h3 class="mt-2 font-medium">{{ title }}</h3>
    <p v-if="description" class="mt-1 max-w-md text-sm text-muted-foreground">{{ description }}</p>
    <div class="mt-4 flex gap-2"><slot /></div>
  </div>
</template>
