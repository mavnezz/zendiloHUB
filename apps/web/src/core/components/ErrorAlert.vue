<script setup lang="ts">
import { CircleAlert } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/core/ui/alert'

defineProps<{ title?: string; message: string }>()
</script>

<template>
  <Alert variant="destructive" role="alert" data-test="error">
    <CircleAlert />
    <AlertTitle>{{ title ?? $t('common.error') }}</AlertTitle>
    <AlertDescription>{{ message }}</AlertDescription>
  </Alert>
</template>
