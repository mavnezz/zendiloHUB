<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'

/** Creates or renames a queue or a group: a name and a description; `save` does the request. */
const props = defineProps<{
  title: string
  description: string
  initial: { name: string; description: string } | null
  save: (body: { name: string; description: string }) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const name = ref('')
const text = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    name.value = props.initial?.name ?? ''
    text.value = props.initial?.description ?? ''
    error.value = null
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save({ name: name.value, description: text.value })
    open.value = false
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ description }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="access-name">{{ $t('access.name') }}</Label>
          <Input id="access-name" v-model="name" maxlength="80" required autofocus />
        </div>
        <div class="grid gap-2">
          <Label for="access-description">{{ $t('access.descriptionLabel') }}</Label>
          <Textarea id="access-description" v-model="text" maxlength="500" rows="3" />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !name.trim()" data-test="save">{{ $t('common.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
