<script setup lang="ts">
import { Building2, Mail, Phone, X } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { customersApi } from '@/modules/customers/api'
import { useSession } from '@/modules/identity/session'
import { useTenants } from '@/modules/tenancy/tenants'
import {
  fromLocalInput,
  PENDING_STATES,
  PRIORITIES,
  SETTABLE_STATES,
  ticketsApi,
  toLocalInput,
  type SettableState,
  type TicketChanges,
  type TicketDetail,
} from '../api'
import type { PickedCustomer } from '../customer'
import { useDirectory } from '../directory'
import CustomerPicker from './CustomerPicker.vue'

/** The fields of a ticket next to its messages; each change needs its right in the queue. */
const props = defineProps<{ ticket: TicketDetail }>()
const emit = defineEmits<{ change: [changes: TicketChanges]; unlink: [otherId: string] }>()

const { t } = useI18n()
const tenants = useTenants()
const session = useSession()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)
const rights = computed(() => props.ticket.rights)
const editable = computed(() => rights.value.includes('edit') && props.ticket.state !== 'merged')
const me = computed(() => session.user.value?.id ?? '')

const assignees = ref<string[]>([])
async function loadAssignees(): Promise<void> {
  try {
    assignees.value = await ticketsApi.assignees(tenantId.value, props.ticket.queue_id)
  } catch {
    assignees.value = []
  }
}
onMounted(loadAssignees)
watch(() => props.ticket.queue_id, loadAssignees)

const queueOptions = computed(() => {
  const movable = directory.queues.value.filter(
    (queue) => queue.id === props.ticket.queue_id || queue.rights.includes('create'),
  )
  return movable.map((queue) => ({ value: queue.id, label: queue.name }))
})

const ownerOptions = computed(() => {
  const others = rights.value.includes('assign')
  const ids = assignees.value.filter((id) => others || id === me.value)
  const current = props.ticket.owner_id
  if (current && !ids.includes(current)) {
    ids.unshift(current)
  }
  return [
    { value: '', label: t('tickets.nobody') },
    ...ids.map((id) => ({ value: id, label: id === me.value ? t('tickets.me') : directory.memberName(id) })),
  ]
})
const canChangeOwner = computed(
  () =>
    props.ticket.state !== 'merged' &&
    (rights.value.includes('assign') ||
      (rights.value.includes('reply') && [null, me.value].includes(props.ticket.owner_id))),
)

const memberOptions = computed(() => [
  { value: '', label: t('tickets.nobody') },
  ...directory.members.value.map((member) => ({ value: member.user_id, label: member.email })),
])

const state = ref<SettableState>('open')
const pendingUntil = ref('')
const tags = ref('')
watch(
  () => props.ticket,
  (ticket) => {
    state.value = ticket.state === 'merged' ? 'closed' : ticket.state
    pendingUntil.value = toLocalInput(ticket.pending_until)
    tags.value = ticket.tags.join(', ')
  },
  { immediate: true },
)
const pending = computed(() => PENDING_STATES.includes(state.value))

function changeState(value: SettableState): void {
  state.value = value
  if (!PENDING_STATES.includes(value)) {
    emit('change', { state: value })
  } else if (pendingUntil.value) {
    emit('change', { state: value, pending_until: fromLocalInput(pendingUntil.value) })
  }
}

function changePending(value: string): void {
  pendingUntil.value = value
  if (value && pending.value) {
    emit('change', { state: state.value, pending_until: fromLocalInput(value) })
  }
}

function saveTags(): void {
  const next = tags.value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
  if (next.join(',') !== props.ticket.tags.join(',')) {
    emit('change', { tags: next })
  }
}

const changingCustomer = ref(false)
const picked = ref<PickedCustomer | null>(null)
watch(picked, async (value) => {
  if (!value) {
    return
  }
  try {
    const id =
      value.id ??
      (
        await customersApi.createContact(tenantId.value, {
          name: '',
          notes: '',
          email: value.email ?? null,
          phone: value.phone ?? null,
        })
      ).id
    emit('change', { customer_id: id })
    changingCustomer.value = false
  } catch (caught) {
    notify.error(caught)
  }
  picked.value = null
})
</script>

<template>
  <div class="grid gap-4 text-sm">
    <section class="grid gap-2 rounded-lg border p-3" data-test="customer-card">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">{{ $t('tickets.customer') }}</h3>
        <Button
          v-if="editable"
          variant="ghost"
          size="sm"
          class="h-6 px-2 text-xs"
          data-test="change-customer"
          @click="changingCustomer = !changingCustomer"
          >{{ changingCustomer ? $t('common.cancel') : $t('tickets.changeCustomer') }}</Button
        >
      </div>
      <CustomerPicker v-if="changingCustomer" v-model="picked" />
      <template v-else-if="ticket.customer">
        <RouterLink
          v-if="tenants.can('customers.view')"
          :to="{ name: 'contact', params: { tenantId, contactId: ticket.customer.id } }"
          class="font-medium hover:underline"
          data-test="customer-link"
          >{{ ticket.customer.name }}</RouterLink
        >
        <span v-else class="font-medium">{{ ticket.customer.name }}</span>
        <span v-if="ticket.customer.email" class="flex items-center gap-2 text-muted-foreground"
          ><Mail class="size-3.5" />{{ ticket.customer.email }}</span
        >
        <span v-if="ticket.customer.phone" class="flex items-center gap-2 text-muted-foreground"
          ><Phone class="size-3.5" />{{ ticket.customer.phone }}</span
        >
        <span v-if="ticket.customer.company_name" class="flex items-center gap-2 text-muted-foreground"
          ><Building2 class="size-3.5" />{{ ticket.customer.company_name }}</span
        >
      </template>
      <span v-else class="text-muted-foreground">{{ $t('tickets.noCustomer') }}</span>
    </section>

    <div class="grid gap-1.5">
      <Label for="field-queue">{{ $t('tickets.queue') }}</Label>
      <NativeSelect
        id="field-queue"
        :model-value="ticket.queue_id"
        :options="queueOptions"
        :disabled="!rights.includes('move') || ticket.state === 'merged'"
        @update:model-value="(value: string) => emit('change', { queue_id: value })"
      />
    </div>
    <div class="grid gap-1.5">
      <Label for="field-state">{{ $t('tickets.state') }}</Label>
      <NativeSelect
        id="field-state"
        :model-value="state"
        :options="SETTABLE_STATES.map((value) => ({ value, label: $t(`tickets.states.${value}`) }))"
        :disabled="!editable"
        @update:model-value="changeState"
      />
    </div>
    <div v-if="pending" class="grid gap-1.5">
      <Label for="field-pending">{{ $t('tickets.pendingUntil') }}</Label>
      <Input
        id="field-pending"
        type="datetime-local"
        :model-value="pendingUntil"
        :disabled="!editable"
        @change="(event: Event) => changePending((event.target as HTMLInputElement).value)"
      />
    </div>
    <div class="grid gap-1.5">
      <Label for="field-priority">{{ $t('tickets.priority') }}</Label>
      <NativeSelect
        id="field-priority"
        :model-value="ticket.priority"
        :options="PRIORITIES.map((value) => ({ value, label: $t(`tickets.priorities.${value}`) }))"
        :disabled="!editable"
        @update:model-value="(value) => emit('change', { priority: value })"
      />
    </div>
    <div class="grid gap-1.5">
      <Label for="field-owner">{{ $t('tickets.owner') }}</Label>
      <NativeSelect
        id="field-owner"
        :model-value="ticket.owner_id ?? ''"
        :options="ownerOptions"
        :disabled="!canChangeOwner"
        @update:model-value="(value: string) => emit('change', { owner_id: value || null })"
      />
    </div>
    <div class="grid gap-1.5">
      <Label for="field-responsible">{{ $t('tickets.responsible') }}</Label>
      <NativeSelect
        id="field-responsible"
        :model-value="ticket.responsible_id ?? ''"
        :options="memberOptions"
        :disabled="!editable"
        @update:model-value="(value: string) => emit('change', { responsible_id: value || null })"
      />
    </div>
    <div class="grid gap-1.5">
      <Label for="field-tags">{{ $t('tickets.tags') }}</Label>
      <Input
        id="field-tags"
        v-model="tags"
        :disabled="!editable"
        :placeholder="$t('tickets.tagsPlaceholder')"
        @keydown.enter.prevent="saveTags"
        @blur="saveTags"
      />
    </div>
    <p class="text-xs text-muted-foreground" data-test="time-total">
      {{ $t('tickets.timeTotal', { minutes: ticket.time_minutes }) }}
    </p>
    <section v-if="ticket.links.length" class="grid gap-1.5">
      <h3 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">{{ $t('tickets.links') }}</h3>
      <div
        v-for="link in ticket.links"
        :key="link.id"
        class="flex items-center gap-2"
        :data-test="`link-${link.number}`"
      >
        <RouterLink :to="{ name: 'ticket', params: { tenantId, ticketId: link.id } }" class="truncate hover:underline">
          #{{ link.number }} {{ link.subject }}
        </RouterLink>
        <span class="text-xs text-muted-foreground">{{ $t(`tickets.linkKinds.${link.kind}`) }}</span>
        <Button
          v-if="editable"
          variant="ghost"
          size="icon"
          class="ml-auto size-6"
          :aria-label="$t('tickets.unlink')"
          :data-test="`unlink-${link.number}`"
          @click="emit('unlink', link.id)"
          ><X class="size-3.5"
        /></Button>
      </div>
    </section>
  </div>
</template>
