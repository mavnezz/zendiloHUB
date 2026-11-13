<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { Button } from '@/core/ui/button'
</script>

<template>
  <section class="mx-auto max-w-xl px-4 py-24 text-center">
    <h1 class="text-2xl font-semibold">{{ $t('notFound.title') }}</h1>
    <p class="mt-2 text-muted-foreground">{{ $t('notFound.text') }}</p>
    <Button as-child class="mt-6">
      <RouterLink :to="{ name: 'start' }">{{ $t('notFound.back') }}</RouterLink>
    </Button>
  </section>
</template>
