<script setup lang="ts">
import { CalendarClock, Pencil, Plus, Timer, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { timezones } from '@/core/timezones'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import { Textarea } from '@/core/ui/textarea'
import { accessApi } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { PRIORITIES } from '@/modules/tickets/api'
import { serviceApi, WEEKDAYS, type Calendar, type Policy, type Weekday } from '../api'

/** Business hours with holidays, and the response and solution times of tickets. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const setup = useAsyncData(() => serviceApi.setup(tenantId.value))
const queues = useAsyncData(() => accessApi.queues(tenantId.value))
const manage = computed(() => tenants.can('service.manage'))

function minutes(value: number | null | undefined): string {
  if (!value) {
    return '–'
  }
  return value % 60 === 0 ? t('service.hours', { count: value / 60 }) : t('service.minutes', { count: value })
}

// Calendars
const calendarOpen = ref(false)
const calendarEditing = ref<Calendar | null>(null)
const calendarForm = ref({ name: '', timezone: 'Europe/Berlin', hours: {} as Record<Weekday, string>, holidays: '' })
const calendarError = ref<string | null>(null)

function openCalendar(calendar: Calendar | null): void {
  calendarEditing.value = calendar
  const hours = {} as Record<Weekday, string>
  for (const day of WEEKDAYS) {
    const intervals = calendar ? (calendar.hours[day] ?? []) : ['sat', 'sun'].includes(day) ? [] : [['08:00', '17:00']]
    hours[day] = intervals.map(([start, end]) => `${start}-${end}`).join(', ')
  }
  calendarForm.value = {
    name: calendar?.name ?? '',
    timezone: calendar?.timezone ?? tenants.current.value?.timezone ?? 'Europe/Berlin',
    hours,
    holidays: (calendar?.holidays ?? []).join('\n'),
  }
  calendarError.value = null
  calendarOpen.value = true
}

async function saveCalendar(): Promise<void> {
  calendarError.value = null
  const hours: Record<string, [string, string][]> = {}
  for (const day of WEEKDAYS) {
    hours[day] = (calendarForm.value.hours[day] ?? '')
      .split(',')
      .map((each) => each.trim())
      .filter(Boolean)
      .map((each) => each.split('-').map((part) => part.trim()) as [string, string])
  }
  const body = {
    name: calendarForm.value.name,
    timezone: calendarForm.value.timezone,
    hours,
    holidays: calendarForm.value.holidays
      .split('\n')
      .map((each) => each.trim())
      .filter(Boolean),
  }
  try {
    const saved = calendarEditing.value
      ? await serviceApi.updateCalendar(tenantId.value, calendarEditing.value.id, body)
      : await serviceApi.createCalendar(tenantId.value, body)
    notify.success(t('service.saved', { name: saved.name }))
    calendarOpen.value = false
    await setup.reload()
  } catch (caught) {
    calendarError.value = errorText(caught)
  }
}

// Policies
const policyOpen = ref(false)
const policyEditing = ref<Policy | null>(null)
const policyForm = ref({
  name: '',
  active: true,
  queue_ids: [] as string[],
  priorities: [] as string[],
  first: '',
  solution: '',
  calendar_id: '',
})
const policyError = ref<string | null>(null)

function openPolicy(policy: Policy | null): void {
  policyEditing.value = policy
  policyForm.value = {
    name: policy?.name ?? '',
    active: policy?.active ?? true,
    queue_ids: [...(policy?.queue_ids ?? [])],
    priorities: [...(policy?.priorities ?? [])],
    first: policy?.first_response_minutes ? String(policy.first_response_minutes) : '',
    solution: policy?.solution_minutes ? String(policy.solution_minutes) : '',
    calendar_id: policy?.calendar_id ?? '',
  }
  policyError.value = null
  policyOpen.value = true
}

function toggle(values: string[], value: string, on: boolean): void {
  const index = values.indexOf(value)
  if (on && index < 0) {
    values.push(value)
  } else if (!on && index >= 0) {
    values.splice(index, 1)
  }
}

async function savePolicy(): Promise<void> {
  policyError.value = null
  const form = policyForm.value
  const body = {
    name: form.name,
    active: form.active,
    queue_ids: form.queue_ids,
    priorities: form.priorities as never,
    first_response_minutes: form.first ? Number(form.first) : null,
    solution_minutes: form.solution ? Number(form.solution) : null,
    calendar_id: form.calendar_id || null,
  }
  try {
    const saved = policyEditing.value
      ? await serviceApi.updatePolicy(tenantId.value, policyEditing.value.id, body)
      : await serviceApi.createPolicy(tenantId.value, body)
    notify.success(t('service.saved', { name: saved.name }))
    policyOpen.value = false
    await setup.reload()
  } catch (caught) {
    policyError.value = errorText(caught)
  }
}

const deleting = ref<{ kind: 'calendar' | 'policy'; id: string; name: string } | null>(null)
const deleteOpen = ref(false)
function askDelete(kind: 'calendar' | 'policy', id: string, name: string): void {
  deleting.value = { kind, id, name }
  deleteOpen.value = true
}
async function remove(): Promise<void> {
  const target = deleting.value!
  await (target.kind === 'calendar'
    ? serviceApi.deleteCalendar(tenantId.value, target.id)
    : serviceApi.deletePolicy(tenantId.value, target.id))
  notify.success(t('service.deleted', { name: target.name }))
  await setup.reload()
}

function scope(policy: Policy): string {
  const queuesText = policy.queue_ids.length
    ? policy.queue_ids.map((id) => queues.data.value?.find((queue) => queue.id === id)?.name ?? '?').join(', ')
    : t('service.allQueues')
  const priorities = policy.priorities.length
    ? policy.priorities.map((value) => t(`tickets.priorities.${value}`)).join(', ')
    : t('service.allPriorities')
  return `${queuesText} · ${priorities}`
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('service.title')" :description="$t('service.description')" />
    <ErrorAlert v-if="setup.error.value" :message="setup.error.value" />
    <template v-else-if="setup.data.value">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center justify-between text-base">
            <span class="flex items-center gap-2"><Timer class="size-4" /> {{ $t('service.policies') }}</span>
            <Button v-if="manage" size="sm" variant="outline" data-test="create-policy" @click="openPolicy(null)"
              ><Plus class="size-4" /> {{ $t('service.createPolicy') }}</Button
            >
          </CardTitle>
          <CardDescription>{{ $t('service.policiesHint') }}</CardDescription>
        </CardHeader>
        <CardContent class="grid gap-2">
          <p v-if="!setup.data.value.policies.length" class="text-sm text-muted-foreground">{{ $t('service.none') }}</p>
          <div
            v-for="policy in setup.data.value.policies"
            :key="policy.id"
            class="flex items-center gap-3 rounded-md border p-3"
            :data-test="`policy-${policy.name}`"
          >
            <div class="min-w-0 flex-1">
              <p class="flex items-center gap-2 font-medium">
                {{ policy.name }}
                <Badge v-if="!policy.active" variant="outline">{{ $t('automation.inactive') }}</Badge>
              </p>
              <p class="text-xs text-muted-foreground">
                {{ scope(policy) }} · {{ $t('service.firstResponse') }}: {{ minutes(policy.first_response_minutes) }} ·
                {{ $t('service.solution') }}: {{ minutes(policy.solution_minutes) }} ·
                {{
                  setup.data.value.calendars.find((each) => each.id === policy.calendar_id)?.name ??
                  $t('service.aroundTheClock')
                }}
              </p>
            </div>
            <template v-if="manage">
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.edit')"
                :data-test="`edit-policy-${policy.name}`"
                @click="openPolicy(policy)"
                ><Pencil class="size-4"
              /></Button>
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.delete')"
                :data-test="`delete-policy-${policy.name}`"
                @click="askDelete('policy', policy.id, policy.name)"
                ><Trash2 class="size-4"
              /></Button>
            </template>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center justify-between text-base">
            <span class="flex items-center gap-2"><CalendarClock class="size-4" /> {{ $t('service.calendars') }}</span>
            <Button v-if="manage" size="sm" variant="outline" data-test="create-calendar" @click="openCalendar(null)"
              ><Plus class="size-4" /> {{ $t('service.createCalendar') }}</Button
            >
          </CardTitle>
          <CardDescription>{{ $t('service.calendarsHint') }}</CardDescription>
        </CardHeader>
        <CardContent class="grid gap-2">
          <p v-if="!setup.data.value.calendars.length" class="text-sm text-muted-foreground">
            {{ $t('service.none') }}
          </p>
          <div
            v-for="calendar in setup.data.value.calendars"
            :key="calendar.id"
            class="flex items-center gap-3 rounded-md border p-3"
            :data-test="`calendar-${calendar.name}`"
          >
            <div class="min-w-0 flex-1">
              <p class="font-medium">{{ calendar.name }}</p>
              <p class="text-xs text-muted-foreground">
                {{ calendar.timezone }} ·
                {{
                  WEEKDAYS.filter((day) => calendar.hours[day]?.length)
                    .map(
                      (day) =>
                        `${$t(`service.days.${day}`)} ${calendar.hours[day]!.map(([start, end]) => `${start}–${end}`).join(', ')}`,
                    )
                    .join(' · ')
                }}
                <template v-if="calendar.holidays.length">
                  · {{ $t('service.holidayCount', { count: calendar.holidays.length }) }}</template
                >
              </p>
            </div>
            <template v-if="manage">
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.edit')"
                :data-test="`edit-calendar-${calendar.name}`"
                @click="openCalendar(calendar)"
                ><Pencil class="size-4"
              /></Button>
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.delete')"
                :data-test="`delete-calendar-${calendar.name}`"
                @click="askDelete('calendar', calendar.id, calendar.name)"
                ><Trash2 class="size-4"
              /></Button>
            </template>
          </div>
        </CardContent>
      </Card>
    </template>

    <Dialog v-model:open="policyOpen">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{{ policyEditing ? $t('service.editPolicy') : $t('service.createPolicy') }}</DialogTitle>
          <DialogDescription>{{ $t('service.policyText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="savePolicy">
          <ErrorAlert v-if="policyError" :message="policyError" />
          <div class="grid gap-4 sm:grid-cols-[1fr_auto]">
            <div class="grid gap-2">
              <Label for="policy-name">{{ $t('automation.name') }}</Label>
              <Input id="policy-name" v-model="policyForm.name" maxlength="80" required autofocus />
            </div>
            <label class="flex items-center gap-3 self-end pb-2 text-sm">
              <Switch v-model="policyForm.active" /> {{ $t('automation.active') }}
            </label>
          </div>
          <div class="grid gap-2">
            <Label>{{ $t('service.forQueues') }}</Label>
            <div class="flex flex-wrap gap-3 text-sm">
              <label v-for="queue in queues.data.value ?? []" :key="queue.id" class="flex items-center gap-2">
                <Checkbox
                  :model-value="policyForm.queue_ids.includes(queue.id)"
                  @update:model-value="(on) => toggle(policyForm.queue_ids, queue.id, on === true)"
                />
                {{ queue.name }}
              </label>
            </div>
          </div>
          <div class="grid gap-2">
            <Label>{{ $t('service.forPriorities') }}</Label>
            <div class="flex flex-wrap gap-3 text-sm">
              <label
                v-for="priority in PRIORITIES"
                :key="priority"
                class="flex items-center gap-2"
                :data-test="`policy-priority-${priority}`"
              >
                <Checkbox
                  :model-value="policyForm.priorities.includes(priority)"
                  @update:model-value="(on) => toggle(policyForm.priorities, priority, on === true)"
                />
                {{ $t(`tickets.priorities.${priority}`) }}
              </label>
            </div>
          </div>
          <div class="grid gap-4 sm:grid-cols-3">
            <div class="grid gap-2">
              <Label for="policy-first">{{ $t('service.firstResponseMinutes') }}</Label>
              <Input id="policy-first" v-model="policyForm.first" type="number" min="1" />
            </div>
            <div class="grid gap-2">
              <Label for="policy-solution">{{ $t('service.solutionMinutes') }}</Label>
              <Input id="policy-solution" v-model="policyForm.solution" type="number" min="1" />
            </div>
            <div class="grid gap-2">
              <Label for="policy-calendar">{{ $t('service.calendar') }}</Label>
              <NativeSelect
                id="policy-calendar"
                v-model="policyForm.calendar_id"
                :options="[
                  { value: '', label: $t('service.aroundTheClock') },
                  ...(setup.data.value?.calendars ?? []).map((each) => ({ value: each.id, label: each.name })),
                ]"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" data-test="save-policy">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="calendarOpen">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{{ calendarEditing ? $t('service.editCalendar') : $t('service.createCalendar') }}</DialogTitle>
          <DialogDescription>{{ $t('service.calendarText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="saveCalendar">
          <ErrorAlert v-if="calendarError" :message="calendarError" />
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="grid gap-2">
              <Label for="calendar-name">{{ $t('automation.name') }}</Label>
              <Input id="calendar-name" v-model="calendarForm.name" maxlength="80" required autofocus />
            </div>
            <div class="grid gap-2">
              <Label for="calendar-timezone">{{ $t('service.timezone') }}</Label>
              <NativeSelect
                id="calendar-timezone"
                v-model="calendarForm.timezone"
                :options="timezones().map((value) => ({ value, label: value }))"
              />
            </div>
          </div>
          <div class="grid gap-2">
            <div v-for="day in WEEKDAYS" :key="day" class="grid grid-cols-[3rem_1fr] items-center gap-2">
              <Label :for="`calendar-${day}`" class="text-xs">{{ $t(`service.days.${day}`) }}</Label>
              <Input :id="`calendar-${day}`" v-model="calendarForm.hours[day]" placeholder="08:00-12:00, 13:00-17:00" />
            </div>
          </div>
          <div class="grid gap-2">
            <Label for="calendar-holidays">{{ $t('service.holidays') }}</Label>
            <Textarea id="calendar-holidays" v-model="calendarForm.holidays" rows="3" placeholder="2026-12-24" />
          </div>
          <DialogFooter>
            <Button type="submit" data-test="save-calendar">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('service.deleteTitle', { name: deleting?.name })"
      :description="$t(`service.deleteText.${deleting?.kind ?? 'policy'}`)"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
