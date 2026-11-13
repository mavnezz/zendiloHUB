<script setup lang="ts">
import { ListPlus, Pencil, Plus, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import { useTenants } from '@/modules/tenancy/tenants'
import { ticketsApi, type TicketField } from '../api'

/** The organization's own fields on every ticket (text, number, choice, yes/no, date). */
type Kind = TicketField['kind']
const KINDS: Kind[] = ['text', 'number', 'select', 'checkbox', 'date']

const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const fields = useAsyncData(() => ticketsApi.fields(tenantId.value))

const editing = ref<TicketField | null>(null)
const dialogOpen = ref(false)
const form = ref<{ key: string; label: string; kind: Kind; options: string }>({
  key: '',
  label: '',
  kind: 'text',
  options: '',
})
const error = ref<string | null>(null)
const deleting = ref<TicketField | null>(null)
const deleteOpen = ref(false)

function openDialog(field: TicketField | null): void {
  editing.value = field
  form.value = {
    key: field?.key ?? '',
    label: field?.label ?? '',
    kind: field?.kind ?? 'text',
    options: (field?.options ?? []).join('\n'),
  }
  error.value = null
  dialogOpen.value = true
}

function guessKey(): void {
  if (!editing.value && !form.value.key) {
    form.value.key = form.value.label
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .replace(/^(\d)/, 'f_$1')
      .slice(0, 40)
  }
}

async function save(): Promise<void> {
  error.value = null
  const body = {
    key: form.value.key,
    label: form.value.label,
    kind: form.value.kind,
    options: form.value.options
      .split('\n')
      .map((each) => each.trim())
      .filter(Boolean),
  }
  try {
    const saved = editing.value
      ? await ticketsApi.updateField(tenantId.value, editing.value.id, body)
      : await ticketsApi.createField(tenantId.value, body)
    notify.success(t('ticketFields.saved', { label: saved.label }))
    dialogOpen.value = false
    await fields.reload()
  } catch (caught) {
    error.value = errorText(caught)
  }
}

function askDelete(field: TicketField): void {
  deleting.value = field
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const field = deleting.value!
  await ticketsApi.deleteField(tenantId.value, field.id)
  notify.success(t('ticketFields.deleted', { label: field.label }))
  await fields.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-4xl gap-6">
    <PageHeader :title="$t('ticketFields.title')" :description="$t('ticketFields.description')">
      <Button data-test="create-field" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('ticketFields.create') }}</Button
      >
    </PageHeader>
    <ErrorAlert v-if="fields.error.value" :message="fields.error.value" />
    <EmptyState
      v-else-if="fields.data.value?.length === 0"
      :title="$t('ticketFields.empty')"
      :description="$t('ticketFields.emptyHint')"
    >
      <template #icon><ListPlus class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="fields.data.value">
      <CardContent class="grid gap-2 pt-6">
        <div
          v-for="field in fields.data.value"
          :key="field.id"
          class="flex items-center gap-3 rounded-md border p-3"
          :data-test="`field-${field.key}`"
        >
          <div class="min-w-0 flex-1">
            <p class="font-medium">{{ field.label }}</p>
            <p class="text-xs text-muted-foreground">
              <code>{{ field.key }}</code> · {{ $t(`ticketFields.kinds.${field.kind}`) }}
              <template v-if="field.options.length"> · {{ field.options.join(', ') }}</template>
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.edit')"
            :data-test="`edit-field-${field.key}`"
            @click="openDialog(field)"
            ><Pencil class="size-4"
          /></Button>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.delete')"
            :data-test="`delete-field-${field.key}`"
            @click="askDelete(field)"
            ><Trash2 class="size-4"
          /></Button>
        </div>
      </CardContent>
    </Card>

    <Dialog v-model:open="dialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ editing ? $t('ticketFields.edit') : $t('ticketFields.create') }}</DialogTitle>
          <DialogDescription>{{ $t('ticketFields.dialogText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="save">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-2">
            <Label for="field-label">{{ $t('ticketFields.label') }}</Label>
            <Input id="field-label" v-model="form.label" maxlength="80" required autofocus @blur="guessKey" />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="grid gap-2">
              <Label for="field-key">{{ $t('ticketFields.key') }}</Label>
              <Input id="field-key" v-model="form.key" maxlength="40" :disabled="!!editing" required />
            </div>
            <div class="grid gap-2">
              <Label for="field-kind">{{ $t('ticketFields.kind') }}</Label>
              <NativeSelect
                id="field-kind"
                v-model="form.kind"
                :disabled="!!editing"
                :options="KINDS.map((value) => ({ value, label: $t(`ticketFields.kinds.${value}`) }))"
              />
            </div>
          </div>
          <div v-if="form.kind === 'select'" class="grid gap-2">
            <Label for="field-options">{{ $t('ticketFields.options') }}</Label>
            <Textarea id="field-options" v-model="form.options" rows="4" />
          </div>
          <DialogFooter>
            <Button type="submit" data-test="save-field">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('ticketFields.deleteTitle', { label: deleting?.label })"
      :description="$t('ticketFields.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
