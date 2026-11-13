<script setup lang="ts">
defineProps<{ page: 'imprint' | 'privacy' | 'terms' }>()
</script>

<template>
  <article class="mx-auto max-w-3xl px-4 py-12">
    <h1 class="text-3xl font-semibold tracking-tight">{{ $t(`legal.${page}`) }}</h1>
    <p class="mt-6 rounded-lg border border-dashed p-6 text-muted-foreground" data-test="legal-placeholder">
      {{ $t('legal.placeholder') }}
    </p>
  </article>
</template>
