<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { LINK_KINDS, type LinkKind } from '../api'

/** Asks for another ticket's number: to merge into it, or to link it (`withKind`). */
const props = defineProps<{
  title: string
  description: string
  confirmLabel: string
  withKind?: boolean
  action: (number: number, kind: LinkKind) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const number = ref('')
const kind = ref<LinkKind>('related')
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    number.value = ''
    kind.value = 'related'
    error.value = null
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.action(Number(number.value.replace('#', '')), kind.value)
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
          <Label for="other-number">{{ $t('tickets.otherNumber') }}</Label>
          <Input id="other-number" v-model="number" inputmode="numeric" placeholder="1001" required autofocus />
        </div>
        <div v-if="withKind" class="grid gap-2">
          <Label for="link-kind">{{ $t('tickets.linkKind') }}</Label>
          <NativeSelect
            id="link-kind"
            v-model="kind"
            :options="LINK_KINDS.map((value) => ({ value, label: $t(`tickets.linkKinds.${value}`) }))"
          />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !/^#?\d+$/.test(number.trim())" data-test="confirm-number">
            {{ confirmLabel }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
