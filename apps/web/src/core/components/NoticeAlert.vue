<script setup lang="ts">
import { CircleCheck } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/core/ui/alert'

defineProps<{ title: string; message?: string }>()
</script>

<template>
  <Alert role="status" data-test="notice">
    <CircleCheck />
    <AlertTitle>{{ title }}</AlertTitle>
    <AlertDescription v-if="message || $slots.default">
      {{ message }}
      <slot />
    </AlertDescription>
  </Alert>
</template>
