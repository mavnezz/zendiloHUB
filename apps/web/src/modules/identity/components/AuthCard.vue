<script setup lang="ts">
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'

defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="flex justify-center px-4 py-12 sm:py-20">
    <Card class="w-full max-w-md">
      <CardHeader class="text-center">
        <CardTitle class="text-xl">{{ title }}</CardTitle>
        <CardDescription v-if="description">{{ description }}</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-4">
        <slot />
      </CardContent>
    </Card>
  </div>
</template>
