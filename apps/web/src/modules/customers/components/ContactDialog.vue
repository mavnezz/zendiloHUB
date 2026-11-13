<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import type { Contact, ContactRequest } from '../api'

/** Creates or changes a contact; `save` does the request. */
const props = defineProps<{
  title: string
  initial: Contact | null
  companies: { id: string; name: string }[]
  save: (body: ContactRequest) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const form = ref({ name: '', email: '', phone: '', company: '', notes: '' })
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    const contact = props.initial
    form.value = {
      name: contact?.name ?? '',
      email: contact?.email ?? '',
      phone: contact?.phone ?? '',
      company: contact?.company?.id ?? '',
      notes: contact?.notes ?? '',
    }
    error.value = null
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  const { name, email, phone, company, notes } = form.value
  try {
    await props.save({ name, email: email || null, phone: phone || null, company_id: company || null, notes })
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
        <DialogDescription>{{ $t('customers.contacts.dialogText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="contact-name">{{ $t('customers.name') }}</Label>
          <Input id="contact-name" v-model="form.name" maxlength="200" autofocus />
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="grid gap-2">
            <Label for="contact-email">{{ $t('customers.email') }}</Label>
            <Input id="contact-email" v-model="form.email" type="email" maxlength="254" />
          </div>
          <div class="grid gap-2">
            <Label for="contact-phone">{{ $t('customers.phone') }}</Label>
            <Input id="contact-phone" v-model="form.phone" maxlength="40" />
          </div>
        </div>
        <div class="grid gap-2">
          <Label for="contact-company">{{ $t('customers.company') }}</Label>
          <NativeSelect
            id="contact-company"
            v-model="form.company"
            :options="[
              { value: '', label: $t('customers.noCompany') },
              ...companies.map((each) => ({ value: each.id, label: each.name })),
            ]"
          />
        </div>
        <div class="grid gap-2">
          <Label for="contact-notes">{{ $t('customers.notes') }}</Label>
          <Textarea id="contact-notes" v-model="form.notes" maxlength="5000" rows="3" />
        </div>
        <DialogFooter>
          <Button
            type="submit"
            :disabled="busy || !(form.name.trim() || form.email.trim() || form.phone.trim())"
            data-test="save-contact"
            >{{ $t('common.save') }}</Button
          >
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
