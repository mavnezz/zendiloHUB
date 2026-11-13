<script setup lang="ts">
import { ArrowLeft, Eye, EyeOff, GitMerge, Link2, Pencil, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { formatDateTime } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/core/ui/tabs'
import { useTenants } from '@/modules/tenancy/tenants'
import {
  ticketsApi,
  type HistoryEntry,
  type LinkKind,
  type TicketChanges,
  type TicketDetail,
  type TicketMessage,
} from '../api'
import Composer from '../components/Composer.vue'
import HistoryList from '../components/HistoryList.vue'
import MessageList from '../components/MessageList.vue'
import NumberDialog from '../components/NumberDialog.vue'
import PriorityBadge from '../components/PriorityBadge.vue'
import StateBadge from '../components/StateBadge.vue'
import TicketFields from '../components/TicketFields.vue'
import { useDirectory } from '../directory'

/** One ticket: its messages and the composer, its fields, history and what can be done with it. */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const tenants = useTenants()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)
const ticketId = computed(() => String(route.params.ticketId))

const ticket = ref<TicketDetail | null>(null)
const messages = ref<TicketMessage[]>([])
const history = ref<HistoryEntry[]>([])
const error = ref<string | null>(null)

async function load(): Promise<void> {
  try {
    const [found, listed, entries] = await Promise.all([
      ticketsApi.get(tenantId.value, ticketId.value),
      ticketsApi.messages(tenantId.value, ticketId.value),
      ticketsApi.history(tenantId.value, ticketId.value),
    ])
    ticket.value = found
    messages.value = listed
    history.value = entries
    error.value = null
  } catch (caught) {
    error.value = errorText(caught)
  }
}

onMounted(async () => {
  await directory.load().catch(() => undefined)
  await load()
})
watch(ticketId, () => void load())

const rights = computed(() => ticket.value?.rights ?? [])
const merged = computed(() => ticket.value?.state === 'merged')

async function change(changes: TicketChanges): Promise<void> {
  try {
    ticket.value = await ticketsApi.update(tenantId.value, ticketId.value, changes)
    history.value = await ticketsApi.history(tenantId.value, ticketId.value)
    notify.success(t('tickets.saved'))
  } catch (caught) {
    notify.error(caught)
    await load()
  }
}

async function toggleWatch(): Promise<void> {
  const current = ticket.value!
  try {
    await (current.watching
      ? ticketsApi.unwatch(tenantId.value, current.id)
      : ticketsApi.watch(tenantId.value, current.id))
    notify.success(t(current.watching ? 'tickets.unwatched' : 'tickets.watched'))
  } catch (caught) {
    notify.error(caught)
  }
  await load()
}

async function unlink(otherId: string): Promise<void> {
  try {
    await ticketsApi.unlink(tenantId.value, ticketId.value, otherId)
  } catch (caught) {
    notify.error(caught)
  }
  await load()
}

const subjectOpen = ref(false)
const subject = ref('')
function editSubject(): void {
  subject.value = ticket.value?.subject ?? ''
  subjectOpen.value = true
}
async function saveSubject(): Promise<void> {
  subjectOpen.value = false
  await change({ subject: subject.value })
}

const mergeOpen = ref(false)
const linkOpen = ref(false)
const deleteOpen = ref(false)

async function mergeInto(number: number): Promise<void> {
  const target = await ticketsApi.merge(tenantId.value, ticketId.value, number)
  notify.success(t('tickets.mergedInto', { number: target.number }))
  await router.push({ name: 'ticket', params: { tenantId: tenantId.value, ticketId: target.id } })
}

async function linkTo(number: number, kind: LinkKind): Promise<void> {
  ticket.value = await ticketsApi.link(tenantId.value, ticketId.value, number, kind)
  notify.success(t('tickets.linked', { number }))
}

async function split(message: TicketMessage): Promise<void> {
  try {
    const created = await ticketsApi.split(tenantId.value, ticketId.value, message.id)
    notify.success(t('tickets.splitDone', { number: created.number }))
    await router.push({ name: 'ticket', params: { tenantId: tenantId.value, ticketId: created.id } })
  } catch (caught) {
    notify.error(caught)
  }
}

async function remove(): Promise<void> {
  await ticketsApi.remove(tenantId.value, ticketId.value)
  notify.success(t('tickets.deleted', { number: ticket.value?.number }))
  await router.push({ name: 'tickets', params: { tenantId: tenantId.value } })
}
</script>

<template>
  <div class="mx-auto grid max-w-7xl gap-6">
    <RouterLink
      :to="{ name: 'tickets', params: { tenantId } }"
      class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      ><ArrowLeft class="size-4" /> {{ $t('tickets.back') }}</RouterLink
    >
    <ErrorAlert v-if="error" :message="error" />
    <template v-else-if="ticket">
      <header class="flex flex-wrap items-start justify-between gap-4">
        <div class="grid gap-1">
          <div class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span class="font-mono" data-test="ticket-number">#{{ ticket.number }}</span>
            <StateBadge :state="ticket.state" />
            <PriorityBadge :priority="ticket.priority" />
            <span>{{ directory.queueName(ticket.queue_id) }}</span>
            <span>· {{ $t('tickets.createdAt', { date: formatDateTime(ticket.created_at) }) }}</span>
          </div>
          <h1 class="flex items-center gap-2 text-2xl font-semibold tracking-tight" data-test="ticket-subject">
            {{ ticket.subject }}
            <Button
              v-if="rights.includes('edit') && !merged"
              variant="ghost"
              size="icon"
              :aria-label="$t('tickets.editSubject')"
              data-test="edit-subject"
              @click="editSubject"
              ><Pencil class="size-4"
            /></Button>
          </h1>
          <p v-if="ticket.merged_into" class="text-sm" data-test="merged-into">
            {{ $t('tickets.wasMerged') }}
            <RouterLink
              :to="{ name: 'ticket', params: { tenantId, ticketId: ticket.merged_into.id } }"
              class="font-medium underline"
              >#{{ ticket.merged_into.number }}</RouterLink
            >
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" data-test="watch" @click="toggleWatch">
            <EyeOff v-if="ticket.watching" class="size-4" /><Eye v-else class="size-4" />
            {{ ticket.watching ? $t('tickets.unwatch') : $t('tickets.watch') }}
          </Button>
          <template v-if="rights.includes('edit') && !merged">
            <Button variant="outline" size="sm" data-test="link" @click="linkOpen = true"
              ><Link2 class="size-4" /> {{ $t('tickets.link') }}</Button
            >
            <Button variant="outline" size="sm" data-test="merge" @click="mergeOpen = true"
              ><GitMerge class="size-4" /> {{ $t('tickets.merge') }}</Button
            >
          </template>
          <Button
            v-if="tenants.can('tickets.delete')"
            variant="outline"
            size="sm"
            data-test="delete"
            @click="deleteOpen = true"
            ><Trash2 class="size-4" /> {{ $t('common.delete') }}</Button
          >
        </div>
      </header>

      <div class="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <Tabs default-value="messages" class="min-w-0">
          <TabsList>
            <TabsTrigger value="messages" data-test="tab-messages">{{
              $t('tickets.messages', { count: messages.length })
            }}</TabsTrigger>
            <TabsTrigger value="history" data-test="tab-history">{{ $t('tickets.historyTitle') }}</TabsTrigger>
          </TabsList>
          <TabsContent value="messages" class="grid gap-6 pt-2">
            <MessageList
              :messages="messages"
              :customer="ticket.customer"
              :can-split="rights.includes('create') && !merged"
              @split="split"
            />
            <Composer v-if="!merged" :ticket="ticket" @sent="load" />
          </TabsContent>
          <TabsContent value="history" class="pt-2">
            <HistoryList :entries="history" />
          </TabsContent>
        </Tabs>
        <aside>
          <TicketFields :ticket="ticket" @change="change" @unlink="unlink" />
        </aside>
      </div>
    </template>

    <Dialog v-model:open="subjectOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ $t('tickets.editSubject') }}</DialogTitle>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="saveSubject">
          <Input id="ticket-subject" v-model="subject" maxlength="250" required autofocus />
          <DialogFooter>
            <Button type="submit" :disabled="!subject.trim()" data-test="save-subject">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <NumberDialog
      v-model:open="mergeOpen"
      :title="$t('tickets.mergeTitle')"
      :description="$t('tickets.mergeText')"
      :confirm-label="$t('tickets.merge')"
      :action="mergeInto"
    />
    <NumberDialog
      v-model:open="linkOpen"
      :title="$t('tickets.linkTitle')"
      :description="$t('tickets.linkText')"
      :confirm-label="$t('tickets.link')"
      with-kind
      :action="linkTo"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('tickets.deleteTitle', { number: ticket?.number })"
      :description="$t('tickets.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
