<script setup lang="ts">
import { Plus, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import { Textarea } from '@/core/ui/textarea'
import type { Queue } from '@/modules/access/api'
import type { Member } from '@/modules/tenancy/api'
import { PRIORITIES, SETTABLE_STATES } from '@/modules/tickets/api'
import {
  CONDITION_FIELDS,
  CONDITION_OPERATORS,
  TRIGGER_EVENTS,
  type Rule,
  type RuleCondition,
  type RuleKind,
  type RuleRequest,
  type TriggerEvent,
} from '../api'

/** A macro, trigger or scheduled job: when it acts (triggers, jobs) and what it does. */
const props = defineProps<{
  kind: RuleKind
  initial: Rule | null
  queues: Queue[]
  members: Member[]
  save: (body: RuleRequest) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const name = ref('')
const active = ref(true)
const event = ref<TriggerEvent>('created')
const conditions = ref<RuleCondition[]>([])
const schedule = ref<{
  states: string[]
  queue_ids: string[]
  owner: 'any' | 'none' | 'set'
  idle_hours: string
  age_hours: string
  pending_passed: boolean
  tags: string
}>({
  states: [] as string[],
  queue_ids: [] as string[],
  owner: 'any',
  idle_hours: '',
  age_hours: '',
  pending_passed: false,
  tags: '',
})
const actions = ref({
  state: '',
  pending_hours: '',
  priority: '',
  queue_id: '',
  owner: '',
  add_tags: '',
  remove_tags: '',
  note: '',
  reply: '',
  notify_emails: '',
  notify_text: '',
})
const error = ref<string | null>(null)
const busy = ref(false)

const list = (text: string) =>
  text
    .split(',')
    .map((each) => each.trim())
    .filter(Boolean)

watch(open, (opened) => {
  if (!opened) {
    return
  }
  const rule = props.initial
  name.value = rule?.name ?? ''
  active.value = rule?.active ?? true
  event.value = rule?.event ?? 'created'
  conditions.value = rule?.conditions.map((each) => ({ ...each })) ?? []
  const found = rule?.schedule
  schedule.value = {
    states: [...(found?.states ?? [])],
    queue_ids: [...(found?.queue_ids ?? [])],
    owner: found?.owner ?? 'any',
    idle_hours: found?.idle_hours ? String(found.idle_hours) : '',
    age_hours: found?.age_hours ? String(found.age_hours) : '',
    pending_passed: found?.pending_passed ?? false,
    tags: (found?.tags ?? []).join(', '),
  }
  const a = rule?.actions
  actions.value = {
    state: a?.state ?? '',
    pending_hours: a?.pending_hours ? String(a.pending_hours) : '',
    priority: a?.priority ?? '',
    queue_id: a?.queue_id ?? '',
    owner: a?.owner_me ? 'me' : a?.unassign ? 'none' : (a?.owner_id ?? ''),
    add_tags: (a?.add_tags ?? []).join(', '),
    remove_tags: (a?.remove_tags ?? []).join(', '),
    note: a?.note ?? '',
    reply: a?.reply ?? '',
    notify_emails: (a?.notify_emails ?? []).join(', '),
    notify_text: a?.notify_text ?? '',
  }
  error.value = null
})

const stateOptions = computed(() => [
  { value: '', label: t('automation.keep') },
  ...SETTABLE_STATES.map((value) => ({ value, label: t(`tickets.states.${value}`) })),
])
const priorityOptions = computed(() => [
  { value: '', label: t('automation.keep') },
  ...PRIORITIES.map((value) => ({ value, label: t(`tickets.priorities.${value}`) })),
])
const queueOptions = computed(() => [
  { value: '', label: t('automation.keep') },
  ...props.queues.map((queue) => ({ value: queue.id, label: queue.name })),
])
const ownerOptions = computed(() => [
  { value: '', label: t('automation.keep') },
  ...(props.kind === 'macro' ? [{ value: 'me', label: t('automation.ownerMe') }] : []),
  { value: 'none', label: t('automation.unassign') },
  ...(props.kind === 'macro' ? [] : props.members.map((member) => ({ value: member.user_id, label: member.email }))),
])
const pending = computed(() => actions.value.state.startsWith('pending'))

function toggleIn(values: string[], value: string, on: boolean): void {
  const index = values.indexOf(value)
  if (on && index < 0) {
    values.push(value)
  } else if (!on && index >= 0) {
    values.splice(index, 1)
  }
}

function body(): RuleRequest {
  const a = actions.value
  const request: RuleRequest = {
    name: name.value,
    active: active.value,
    conditions: [],
    actions: {
      state: (a.state || null) as RuleRequest['actions']['state'],
      pending_hours: pending.value && a.pending_hours ? Number(a.pending_hours) : null,
      priority: (a.priority || null) as RuleRequest['actions']['priority'],
      queue_id: a.queue_id || null,
      owner_id: a.owner && !['me', 'none'].includes(a.owner) ? a.owner : null,
      owner_me: a.owner === 'me',
      unassign: a.owner === 'none',
      add_tags: list(a.add_tags),
      remove_tags: list(a.remove_tags),
      note: a.note,
      reply: props.kind === 'macro' ? '' : a.reply,
      notify_emails: props.kind === 'trigger' ? list(a.notify_emails.replaceAll(/[\s;]+/g, ',')) : [],
      notify_text: props.kind === 'trigger' ? a.notify_text : '',
    },
  }
  if (props.kind === 'trigger') {
    request.event = event.value
    request.conditions = conditions.value
  }
  if (props.kind === 'schedule') {
    const found = schedule.value
    request.schedule = {
      states: found.states as never,
      queue_ids: found.queue_ids,
      priorities: [],
      tags: list(found.tags),
      owner: found.owner,
      idle_hours: found.idle_hours ? Number(found.idle_hours) : null,
      age_hours: found.age_hours ? Number(found.age_hours) : null,
      pending_passed: found.pending_passed,
    }
  }
  return request
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save(body())
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
        <DialogTitle>{{ $t(`automation.${kind}.${initial ? 'edit' : 'create'}`) }}</DialogTitle>
        <DialogDescription>{{ $t(`automation.${kind}.dialogText`) }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-4 sm:grid-cols-[1fr_auto]">
          <div class="grid gap-2">
            <Label for="rule-name">{{ $t('automation.name') }}</Label>
            <Input id="rule-name" v-model="name" maxlength="80" required autofocus />
          </div>
          <label class="flex items-center gap-3 self-end pb-2 text-sm">
            <Switch v-model="active" /> {{ $t('automation.active') }}
          </label>
        </div>

        <fieldset v-if="kind === 'trigger'" class="grid gap-2 rounded-md border p-3">
          <legend class="px-1 text-sm font-medium">{{ $t('automation.when') }}</legend>
          <NativeSelect
            id="rule-event"
            v-model="event"
            :options="TRIGGER_EVENTS.map((value) => ({ value, label: $t(`automation.events.${value}`) }))"
          />
          <div
            v-for="(condition, index) in conditions"
            :key="index"
            class="grid gap-2 sm:grid-cols-[10rem_10rem_1fr_auto]"
            :data-test="`rule-condition-${index}`"
          >
            <NativeSelect
              v-model="condition.field"
              :options="CONDITION_FIELDS.map((value) => ({ value, label: $t(`automation.fields.${value}`) }))"
              :aria-label="$t('automation.field')"
            />
            <NativeSelect
              v-model="condition.operator"
              :options="CONDITION_OPERATORS.map((value) => ({ value, label: $t(`automation.operators.${value}`) }))"
              :aria-label="$t('automation.operator')"
            />
            <NativeSelect
              v-if="condition.field === 'queue_id'"
              v-model="condition.value"
              :options="queues.map((queue) => ({ value: queue.id, label: queue.name }))"
              :aria-label="$t('automation.value')"
            />
            <Input
              v-else-if="!['is_set', 'is_not_set'].includes(condition.operator)"
              v-model="condition.value"
              :aria-label="$t('automation.value')"
            />
            <span v-else />
            <Button
              type="button"
              variant="ghost"
              size="icon"
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
            data-test="add-rule-condition"
            @click="conditions.push({ field: 'subject', operator: 'contains', value: '' })"
            ><Plus class="size-4" /> {{ $t('automation.addCondition') }}</Button
          >
        </fieldset>

        <fieldset v-if="kind === 'schedule'" class="grid gap-3 rounded-md border p-3">
          <legend class="px-1 text-sm font-medium">{{ $t('automation.which') }}</legend>
          <div class="flex flex-wrap gap-3 text-sm">
            <label
              v-for="state in ['new', 'open', 'pending_reminder', 'pending_close']"
              :key="state"
              class="flex items-center gap-2"
              :data-test="`schedule-state-${state}`"
            >
              <Checkbox
                :model-value="schedule.states.includes(state)"
                @update:model-value="(on) => toggleIn(schedule.states, state, on === true)"
              />
              {{ $t(`tickets.states.${state}`) }}
            </label>
          </div>
          <div class="flex flex-wrap gap-3 text-sm">
            <label v-for="queue in queues" :key="queue.id" class="flex items-center gap-2">
              <Checkbox
                :model-value="schedule.queue_ids.includes(queue.id)"
                @update:model-value="(on) => toggleIn(schedule.queue_ids, queue.id, on === true)"
              />
              {{ queue.name }}
            </label>
          </div>
          <div class="grid gap-3 sm:grid-cols-3">
            <div class="grid gap-1">
              <Label for="schedule-idle" class="text-xs">{{ $t('automation.idleHours') }}</Label>
              <Input id="schedule-idle" v-model="schedule.idle_hours" type="number" min="1" />
            </div>
            <div class="grid gap-1">
              <Label for="schedule-age" class="text-xs">{{ $t('automation.ageHours') }}</Label>
              <Input id="schedule-age" v-model="schedule.age_hours" type="number" min="1" />
            </div>
            <div class="grid gap-1">
              <Label for="schedule-owner" class="text-xs">{{ $t('tickets.owner') }}</Label>
              <NativeSelect
                id="schedule-owner"
                v-model="schedule.owner"
                :options="
                  (['any', 'none', 'set'] as const).map((value) => ({ value, label: $t(`automation.owners.${value}`) }))
                "
              />
            </div>
          </div>
          <label class="flex items-center gap-3 text-sm">
            <Switch v-model="schedule.pending_passed" data-test="schedule-pending" />
            {{ $t('automation.pendingPassed') }}
          </label>
        </fieldset>

        <fieldset class="grid gap-3 rounded-md border p-3">
          <legend class="px-1 text-sm font-medium">{{ $t('automation.then') }}</legend>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="grid gap-1">
              <Label for="action-state" class="text-xs">{{ $t('tickets.state') }}</Label>
              <NativeSelect id="action-state" v-model="actions.state" :options="stateOptions" />
            </div>
            <div v-if="pending" class="grid gap-1">
              <Label for="action-pending" class="text-xs">{{ $t('automation.pendingHours') }}</Label>
              <Input id="action-pending" v-model="actions.pending_hours" type="number" min="1" placeholder="24" />
            </div>
            <div class="grid gap-1">
              <Label for="action-priority" class="text-xs">{{ $t('tickets.priority') }}</Label>
              <NativeSelect id="action-priority" v-model="actions.priority" :options="priorityOptions" />
            </div>
            <div class="grid gap-1">
              <Label for="action-queue" class="text-xs">{{ $t('tickets.queue') }}</Label>
              <NativeSelect id="action-queue" v-model="actions.queue_id" :options="queueOptions" />
            </div>
            <div class="grid gap-1">
              <Label for="action-owner" class="text-xs">{{ $t('tickets.owner') }}</Label>
              <NativeSelect id="action-owner" v-model="actions.owner" :options="ownerOptions" />
            </div>
            <div class="grid gap-1">
              <Label for="action-add-tags" class="text-xs">{{ $t('automation.addTags') }}</Label>
              <Input id="action-add-tags" v-model="actions.add_tags" :placeholder="$t('tickets.tagsPlaceholder')" />
            </div>
            <div class="grid gap-1">
              <Label for="action-remove-tags" class="text-xs">{{ $t('automation.removeTags') }}</Label>
              <Input id="action-remove-tags" v-model="actions.remove_tags" />
            </div>
          </div>
          <div class="grid gap-1">
            <Label for="action-note" class="text-xs">{{ $t('automation.note') }}</Label>
            <Textarea id="action-note" v-model="actions.note" rows="2" />
          </div>
          <div v-if="kind !== 'macro'" class="grid gap-1">
            <Label for="action-reply" class="text-xs">{{ $t('automation.reply') }}</Label>
            <Textarea id="action-reply" v-model="actions.reply" rows="3" />
          </div>
          <template v-if="kind === 'trigger'">
            <div class="grid gap-1">
              <Label for="action-notify-emails" class="text-xs">{{ $t('automation.notifyEmails') }}</Label>
              <Input
                id="action-notify-emails"
                v-model="actions.notify_emails"
                type="text"
                :placeholder="$t('automation.notifyEmailsPlaceholder')"
                data-test="notify-emails"
              />
              <p class="text-xs text-muted-foreground">{{ $t('automation.notifyEmailsHint') }}</p>
            </div>
            <div v-if="actions.notify_emails.trim()" class="grid gap-1">
              <Label for="action-notify-text" class="text-xs">{{ $t('automation.notifyText') }}</Label>
              <Textarea id="action-notify-text" v-model="actions.notify_text" rows="2" data-test="notify-text" />
            </div>
          </template>
        </fieldset>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !name.trim()" data-test="save-rule">{{ $t('common.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
