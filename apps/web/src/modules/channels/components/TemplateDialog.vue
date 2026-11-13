<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import type { TemplateKind, TextTemplate } from '../api'
import PlaceholderHelp from './PlaceholderHelp.vue'

/** Writes a signature or salutation with placeholders. */
const props = defineProps<{
  kind: TemplateKind
  initial: TextTemplate | null
  placeholders: readonly string[]
  save: (body: { kind: TemplateKind; name: string; body: string }) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const name = ref('')
const body = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    name.value = props.initial?.name ?? ''
    body.value = props.initial?.body ?? ''
    error.value = null
  }
})

function insert(placeholder: string): void {
  body.value = body.value ? `${body.value}${body.value.endsWith('\n') ? '' : ' '}${placeholder}` : placeholder
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save({ kind: props.kind, name: name.value, body: body.value })
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
    <DialogContent class="sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>{{ $t(`channels.templates.${initial ? 'edit' : 'create'}.${kind}`) }}</DialogTitle>
        <DialogDescription>{{ $t(`channels.templates.hint.${kind}`) }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="template-name">{{ $t('channels.name') }}</Label>
          <Input id="template-name" v-model="name" maxlength="80" required autofocus />
        </div>
        <div class="grid gap-2">
          <Label for="template-body">{{ $t('channels.templates.text') }}</Label>
          <Textarea id="template-body" v-model="body" rows="7" class="font-mono text-sm" required />
          <PlaceholderHelp :placeholders="placeholders" @insert="insert" />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !name.trim() || !body.trim()" data-test="save-template">{{
            $t('common.save')
          }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
