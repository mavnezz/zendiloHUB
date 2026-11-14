<script setup lang="ts">
import { MailCheck } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { Textarea } from '@/core/ui/textarea'
import { accessApi, type Queue } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi, type QueueChannel, type QueueChannelRequest } from '../api'
import PlaceholderHelp from '../components/PlaceholderHelp.vue'

/** How each queue writes: from which account, with which salutation and signature, and its auto reply. */
const { t, locale } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const data = useAsyncData(async () => {
  const [queues, settings, accounts, templates] = await Promise.all([
    accessApi.queues(tenantId.value),
    channelsApi.queueChannels(tenantId.value),
    channelsApi.accounts(tenantId.value),
    channelsApi.templates(tenantId.value),
  ])
  return { queues, settings, accounts, templates }
})

const EMPTY: QueueChannelRequest = {
  account_id: null,
  signature_id: null,
  salutation_id: null,
  auto_reply: false,
  auto_reply_subject: '',
  auto_reply_body: '',
}

function settingsOf(queue: Queue): QueueChannelRequest {
  const found: QueueChannel | undefined = data.data.value?.settings.find((each) => each.queue_id === queue.id)
  return found ? { ...found } : { ...EMPTY }
}

/** The mailboxes whose mail lands in this queue by default. */
function incomingOf(queueId: string): string {
  return (data.data.value?.accounts ?? [])
    .filter((account) => account.queue_id === queueId)
    .map((account) => account.address)
    .join(', ')
}

const accountOptions = computed(() => [
  { value: '', label: t('channels.queues.noAccount') },
  // A mailbox for incoming mail only cannot send.
  ...(data.data.value?.accounts ?? [])
    .filter((account) => account.smtp !== null)
    .map((account) => ({ value: account.id, label: account.address })),
])

function templateOptions(kind: 'signature' | 'salutation') {
  return [
    { value: '', label: t('channels.queues.none') },
    ...(data.data.value?.templates.templates ?? [])
      .filter((template) => template.kind === kind)
      .map((template) => ({ value: template.id, label: template.name })),
  ]
}

async function save(queue: Queue, changes: Partial<QueueChannelRequest>): Promise<void> {
  try {
    await channelsApi.setQueueChannel(tenantId.value, queue.id, { ...settingsOf(queue), ...changes })
    notify.success(t('channels.queues.saved', { name: queue.name }))
  } catch (caught) {
    notify.error(caught)
  }
  await data.reload()
}

/** A starting text for the auto reply (placeholders are not translated, so they stay out of the messages). */
const AUTO_DEFAULTS: Record<string, { subject: string; body: string }> = {
  de: {
    subject: 'Ihre Anfrage: {{ticket.subject}}',
    body: 'Hallo {{customer.name}},\n\nvielen Dank für Ihre Nachricht. Wir haben sie unter der Nummer #{{ticket.number}} erfasst und melden uns so bald wie möglich.\n\nIhr Team von {{organization.name}}',
  },
  en: {
    subject: 'Your request: {{ticket.subject}}',
    body: 'Hello {{customer.name}},\n\nthank you for your message. We filed it as #{{ticket.number}} and will get back to you as soon as we can.\n\nYour team at {{organization.name}}',
  },
}

const autoQueue = ref<Queue | null>(null)
const autoOpen = ref(false)
const auto = ref({ auto_reply: false, auto_reply_subject: '', auto_reply_body: '' })
const autoError = ref<string | null>(null)

function defaults(): { subject: string; body: string } {
  return AUTO_DEFAULTS[locale.value] ?? AUTO_DEFAULTS.en!
}

function openAuto(queue: Queue): void {
  const current = settingsOf(queue)
  autoQueue.value = queue
  auto.value = {
    auto_reply: current.auto_reply ?? false,
    auto_reply_subject: current.auto_reply_subject || defaults().subject,
    auto_reply_body: current.auto_reply_body || defaults().body,
  }
  autoError.value = null
  autoOpen.value = true
}

async function saveAuto(): Promise<void> {
  const queue = autoQueue.value!
  try {
    await channelsApi.setQueueChannel(tenantId.value, queue.id, { ...settingsOf(queue), ...auto.value })
    notify.success(t('channels.queues.saved', { name: queue.name }))
    autoOpen.value = false
    await data.reload()
  } catch (caught) {
    autoError.value = errorText(caught)
  }
}
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <PageHeader :title="$t('channels.queues.title')" :description="$t('channels.queues.description')" />
    <ErrorAlert v-if="data.error.value" :message="data.error.value" />
    <Card v-else-if="data.data.value">
      <CardContent class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('tickets.queue') }}</TableHead>
              <TableHead>{{ $t('channels.queues.incoming') }}</TableHead>
              <TableHead>{{ $t('channels.queues.account') }}</TableHead>
              <TableHead>{{ $t('channels.templates.kinds.salutation') }}</TableHead>
              <TableHead>{{ $t('channels.templates.kinds.signature') }}</TableHead>
              <TableHead>{{ $t('channels.queues.autoReply') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="queue in data.data.value.queues" :key="queue.id" :data-test="`queue-${queue.id}`">
              <TableCell class="font-medium">{{ queue.name }}</TableCell>
              <TableCell class="text-xs text-muted-foreground" :data-test="`incoming-${queue.id}`">
                {{ incomingOf(queue.id) || '–' }}
              </TableCell>
              <TableCell>
                <NativeSelect
                  :model-value="settingsOf(queue).account_id ?? ''"
                  :options="accountOptions"
                  :aria-label="$t('channels.queues.account')"
                  class="w-56"
                  @update:model-value="(value: string) => save(queue, { account_id: value || null })"
                />
                <p
                  v-if="!settingsOf(queue).account_id"
                  class="mt-1 max-w-56 text-xs text-muted-foreground"
                  :data-test="`fallback-${queue.id}`"
                >
                  {{ $t('channels.queues.fallback') }}
                </p>
              </TableCell>
              <TableCell>
                <NativeSelect
                  :model-value="settingsOf(queue).salutation_id ?? ''"
                  :options="templateOptions('salutation')"
                  :aria-label="$t('channels.templates.kinds.salutation')"
                  class="w-44"
                  @update:model-value="(value: string) => save(queue, { salutation_id: value || null })"
                />
              </TableCell>
              <TableCell>
                <NativeSelect
                  :model-value="settingsOf(queue).signature_id ?? ''"
                  :options="templateOptions('signature')"
                  :aria-label="$t('channels.templates.kinds.signature')"
                  class="w-44"
                  @update:model-value="(value: string) => save(queue, { signature_id: value || null })"
                />
              </TableCell>
              <TableCell>
                <Button variant="outline" size="sm" :data-test="`auto-${queue.id}`" @click="openAuto(queue)">
                  <MailCheck class="size-4" />
                  <Badge v-if="settingsOf(queue).auto_reply" variant="secondary">{{ $t('channels.queues.on') }}</Badge>
                  <span v-else>{{ $t('channels.queues.off') }}</span>
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <Dialog v-model:open="autoOpen">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{{ $t('channels.queues.autoTitle', { name: autoQueue?.name }) }}</DialogTitle>
          <DialogDescription>{{ $t('channels.queues.autoText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="saveAuto">
          <ErrorAlert v-if="autoError" :message="autoError" />
          <label class="flex items-center gap-3 text-sm">
            <Switch v-model="auto.auto_reply" data-test="auto-on" />
            {{ $t('channels.queues.autoOn') }}
          </label>
          <div class="grid gap-2">
            <Label for="auto-subject">{{ $t('channels.queues.autoSubject') }}</Label>
            <Input id="auto-subject" v-model="auto.auto_reply_subject" maxlength="250" />
          </div>
          <div class="grid gap-2">
            <Label for="auto-body">{{ $t('channels.templates.text') }}</Label>
            <Textarea id="auto-body" v-model="auto.auto_reply_body" rows="7" class="font-mono text-sm" />
            <PlaceholderHelp
              :placeholders="data.data.value?.templates.placeholders ?? []"
              @insert="(placeholder) => (auto.auto_reply_body += placeholder)"
            />
          </div>
          <DialogFooter>
            <Button type="submit" data-test="save-auto">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>
