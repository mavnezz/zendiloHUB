<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import type { Company, CompanyRequest } from '../api'

/** Creates or changes a company; `save` does the request. */
const props = defineProps<{
  title: string
  initial: Company | null
  save: (body: CompanyRequest) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const form = ref({ name: '', domain: '', notes: '' })
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    form.value = {
      name: props.initial?.name ?? '',
      domain: props.initial?.domain ?? '',
      notes: props.initial?.notes ?? '',
    }
    error.value = null
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save({ name: form.value.name, domain: form.value.domain || null, notes: form.value.notes })
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
        <DialogDescription>{{ $t('customers.companies.dialogText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="company-name">{{ $t('customers.name') }}</Label>
          <Input id="company-name" v-model="form.name" maxlength="200" required autofocus />
        </div>
        <div class="grid gap-2">
          <Label for="company-domain">{{ $t('customers.domain') }}</Label>
          <Input id="company-domain" v-model="form.domain" maxlength="253" placeholder="example.org" />
          <p class="text-xs text-muted-foreground">{{ $t('customers.companies.domainHint') }}</p>
        </div>
        <div class="grid gap-2">
          <Label for="company-notes">{{ $t('customers.notes') }}</Label>
          <Textarea id="company-notes" v-model="form.notes" maxlength="5000" rows="3" />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !form.name.trim()" data-test="save-company">{{
            $t('common.save')
          }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
