<script setup lang="ts">
import { Button } from '@/core/ui/button'

/** Previous/next below a list, with a count on the left. */
defineProps<{ label: string; hasPrevious: boolean; hasNext: boolean }>()
defineEmits<{ move: [delta: number] }>()
</script>

<template>
  <div class="mt-4 flex items-center justify-between text-sm text-muted-foreground">
    <span data-test="count">{{ label }}</span>
    <div class="flex gap-2">
      <Button variant="outline" size="sm" :disabled="!hasPrevious" data-test="previous" @click="$emit('move', -1)">
        {{ $t('common.previous') }}
      </Button>
      <Button variant="outline" size="sm" :disabled="!hasNext" data-test="next" @click="$emit('move', 1)">
        {{ $t('common.next') }}
      </Button>
    </div>
  </div>
</template>
