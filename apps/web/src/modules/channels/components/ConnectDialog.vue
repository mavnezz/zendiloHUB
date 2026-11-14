<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import type { Queue } from '@/modules/access/api'
import type { ConnectStart, MailProvider } from '../api'

/** A new mailbox at Google or Microsoft 365: name and queue here, then the provider's sign-in page. */
const props = defineProps<{
  provider: MailProvider | null
  queues: Queue[]
  connect: (body: ConnectStart) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const form = ref({ name: '', display_name: '', queue_id: '' })
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    form.value = { name: '', display_name: '', queue_id: props.queues[0]?.id ?? '' }
    error.value = null
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.connect({ provider: props.provider!, ...form.value })
  } catch (caught) {
    error.value = errorText(caught)
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ $t(`channels.accounts.connect.${provider ?? 'google'}`) }}</DialogTitle>
        <DialogDescription>{{ $t('channels.accounts.connect.text') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="connect-name">{{ $t('channels.name') }}</Label>
          <Input
            id="connect-name"
            v-model="form.name"
            maxlength="80"
            :placeholder="$t('channels.accounts.connect.namePlaceholder')"
          />
        </div>
        <div class="grid gap-2">
          <Label for="connect-display">{{ $t('channels.accounts.displayName') }}</Label>
          <Input
            id="connect-display"
            v-model="form.display_name"
            maxlength="80"
            :placeholder="$t('channels.accounts.displayNamePlaceholder')"
          />
        </div>
        <div class="grid gap-2">
          <Label for="connect-queue">{{ $t('channels.accounts.queue') }}</Label>
          <NativeSelect
            id="connect-queue"
            v-model="form.queue_id"
            :options="queues.map((queue) => ({ value: queue.id, label: queue.name }))"
          />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !form.queue_id" data-test="start-connect">
            {{ $t('channels.accounts.connect.go') }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
