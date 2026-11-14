<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { useDirectory } from '@/modules/tickets/directory'
import type { FollowMode } from '../api'
import { useFollowedQueues } from '../followed'

/** Which queues the caller follows, and how: new tickets only, or also every customer reply. */
const open = defineModel<boolean>('open', { required: true })
const { t } = useI18n()
const directory = useDirectory()
const followed = useFollowedQueues()
const error = ref<string | null>(null)

const options = computed(() => [
  { value: '', label: t('notifications.followed.modes.off') },
  { value: 'new', label: t('notifications.followed.modes.new') },
  { value: 'all', label: t('notifications.followed.modes.all') },
])

watch(open, async (opened) => {
  if (!opened) {
    return
  }
  error.value = null
  try {
    await Promise.all([directory.load(), followed.load(true)])
  } catch (caught) {
    error.value = errorText(caught)
  }
})

async function choose(queueId: string, value: string): Promise<void> {
  error.value = null
  try {
    await followed.set(queueId, (value || null) as FollowMode | null)
  } catch (caught) {
    error.value = errorText(caught)
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ $t('notifications.followed.title') }}</DialogTitle>
        <DialogDescription>{{ $t('notifications.followed.description') }}</DialogDescription>
      </DialogHeader>
      <ErrorAlert v-if="error" :message="error" />
      <p v-if="!directory.queues.value.length" class="text-sm text-muted-foreground">
        {{ $t('notifications.followed.none') }}
      </p>
      <div class="grid max-h-96 gap-2 overflow-y-auto">
        <label
          v-for="queue in directory.queues.value"
          :key="queue.id"
          class="flex items-center justify-between gap-3 text-sm"
          :data-test="`follow-${queue.name}`"
        >
          <span class="truncate">{{ queue.name }}</span>
          <NativeSelect
            :model-value="followed.modeOf(queue.id) ?? ''"
            :options="options"
            class="w-56"
            :aria-label="queue.name"
            @update:model-value="(value: string) => choose(queue.id, value)"
          />
        </label>
      </div>
    </DialogContent>
  </Dialog>
</template>
