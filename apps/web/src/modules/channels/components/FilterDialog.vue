<script setup lang="ts">
import { Plus, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import SegmentedControl from '@/core/components/SegmentedControl.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import type { Queue } from '@/modules/access/api'
import { PRIORITIES, type Priority } from '@/modules/tickets/api'
import {
  FILTER_FIELDS,
  OPERATORS,
  type Condition,
  type EmailAccount,
  type FilterRequest,
  type MailFilter,
} from '../api'

/**
 * A rule for incoming mail: conditions (all or any), then route, set the priority, add tags or drop it. It belongs to
 * one mailbox (its rules) or to all mailboxes.
 */
const props = defineProps<{
  initial: MailFilter | null
  queues: Queue[]
  accounts: EmailAccount[]
  /** The mailbox a new filter belongs to; null: all mailboxes. */
  scope: string | null
  save: (body: FilterRequest) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const name = ref('')
const active = ref(true)
const match = ref<'all' | 'any'>('all')
const stop = ref(false)
const conditions = ref<Condition[]>([])
const queueId = ref('')
const priority = ref<Priority | ''>('')
const tags = ref('')
const ignore = ref(false)
const accountId = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (!opened) {
    return
  }
  const found = props.initial
  name.value = found?.name ?? ''
  active.value = found?.active ?? true
  match.value = found?.match ?? 'all'
  accountId.value = (found ? found.account_id : props.scope) ?? ''
  // A mailbox's rule usually decides: the first one that matches routes the mail.
  stop.value = found?.stop ?? Boolean(props.scope)
  conditions.value = found
    ? found.conditions.map((each) => ({ ...each }))
    : [{ field: 'subject', operator: 'contains', value: '', header: '' }]
  queueId.value = found?.actions.queue_id ?? ''
  priority.value = found?.actions.priority ?? ''
  tags.value = (found?.actions.tags ?? []).join(', ')
  ignore.value = found?.actions.ignore ?? false
  error.value = null
})

const fieldOptions = computed(() =>
  FILTER_FIELDS.map((value) => ({ value, label: t(`channels.filters.fields.${value}`) })),
)
const operatorOptions = computed(() =>
  OPERATORS.map((value) => ({ value, label: t(`channels.filters.operators.${value}`) })),
)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save({
      name: name.value,
      active: active.value,
      match: match.value,
      stop: stop.value,
      account_id: accountId.value || null,
      conditions: conditions.value,
      actions: {
        queue_id: ignore.value ? null : queueId.value || null,
        priority: ignore.value ? null : priority.value || null,
        tags: ignore.value
          ? []
          : tags.value
              .split(',')
              .map((tag) => tag.trim())
              .filter(Boolean),
        ignore: ignore.value,
      },
    })
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
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ initial ? $t('channels.filters.edit') : $t('channels.filters.create') }}</DialogTitle>
        <DialogDescription>{{ $t('channels.filters.dialogText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-4 sm:grid-cols-[1fr_auto]">
          <div class="grid gap-2">
            <Label for="filter-name">{{ $t('channels.name') }}</Label>
            <Input id="filter-name" v-model="name" maxlength="80" required autofocus />
          </div>
          <label class="flex items-center gap-3 self-end pb-2 text-sm">
            <Switch v-model="active" /> {{ $t('channels.filters.active') }}
          </label>
        </div>
        <div class="grid gap-2">
          <Label for="filter-scope">{{ $t('channels.filters.scope') }}</Label>
          <NativeSelect
            id="filter-scope"
            v-model="accountId"
            data-test="filter-scope"
            :options="[
              { value: '', label: $t('channels.filters.everyMailbox') },
              ...accounts.map((account) => ({ value: account.id, label: account.address })),
            ]"
          />
        </div>
        <fieldset class="grid gap-2 rounded-md border p-3">
          <legend class="flex items-center gap-2 px-1 text-sm font-medium">{{ $t('channels.filters.when') }}</legend>
          <SegmentedControl
            v-model="match"
            :label="$t('channels.filters.when')"
            :options="[
              { value: 'all', label: $t('channels.filters.all') },
              { value: 'any', label: $t('channels.filters.any') },
            ]"
          />
          <div
            v-for="(condition, index) in conditions"
            :key="index"
            class="grid gap-2 sm:grid-cols-[9rem_10rem_1fr_auto]"
            :data-test="`condition-${index}`"
          >
            <NativeSelect
              v-model="condition.field"
              :options="fieldOptions"
              :aria-label="$t('channels.filters.field')"
            />
            <NativeSelect
              v-model="condition.operator"
              :options="operatorOptions"
              :aria-label="$t('channels.filters.operator')"
            />
            <div class="flex gap-2">
              <Input
                v-if="condition.field === 'header'"
                v-model="condition.header"
                class="w-36"
                placeholder="X-Spam-Flag"
                :aria-label="$t('channels.filters.header')"
              />
              <Input v-model="condition.value" required :aria-label="$t('channels.filters.value')" />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              :disabled="conditions.length === 1"
              :aria-label="$t('common.remove')"
              @click="conditions.splice(index, 1)"
              ><X class="size-4"
            /></Button>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            class="justify-self-start"
            :disabled="conditions.length >= 10"
            data-test="add-condition"
            @click="conditions.push({ field: 'from', operator: 'contains', value: '', header: '' })"
            ><Plus class="size-4" /> {{ $t('channels.filters.addCondition') }}</Button
          >
        </fieldset>
        <fieldset class="grid gap-3 rounded-md border p-3">
          <legend class="px-1 text-sm font-medium">{{ $t('channels.filters.then') }}</legend>
          <label class="flex items-center gap-3 text-sm">
            <Switch v-model="ignore" data-test="filter-ignore" /> {{ $t('channels.filters.ignore') }}
          </label>
          <div v-if="!ignore" class="grid gap-3 sm:grid-cols-3">
            <div class="grid gap-1">
              <Label for="filter-queue" class="text-xs">{{ $t('channels.filters.queue') }}</Label>
              <NativeSelect
                id="filter-queue"
                v-model="queueId"
                :options="[
                  { value: '', label: $t('channels.filters.keep') },
                  ...queues.map((queue) => ({ value: queue.id, label: queue.name })),
                ]"
              />
            </div>
            <div class="grid gap-1">
              <Label for="filter-priority" class="text-xs">{{ $t('tickets.priority') }}</Label>
              <NativeSelect
                id="filter-priority"
                v-model="priority"
                :options="[
                  { value: '' as const, label: $t('channels.filters.keep') },
                  ...PRIORITIES.map((value) => ({ value, label: $t(`tickets.priorities.${value}`) })),
                ]"
              />
            </div>
            <div class="grid gap-1">
              <Label for="filter-tags" class="text-xs">{{ $t('tickets.tags') }}</Label>
              <Input id="filter-tags" v-model="tags" :placeholder="$t('tickets.tagsPlaceholder')" />
            </div>
          </div>
          <label class="flex items-center gap-3 text-sm">
            <Switch v-model="stop" data-test="filter-stop" /> {{ $t('channels.filters.stop') }}
          </label>
        </fieldset>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !name.trim()" data-test="save-filter">{{
            $t('common.save')
          }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
