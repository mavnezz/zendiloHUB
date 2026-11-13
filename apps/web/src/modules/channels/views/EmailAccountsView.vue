<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Mail, Pencil, Plug, Plus, RefreshCw, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDateTime } from '@/core/format'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { accessApi } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi, type AccountRequest, type EmailAccount, type Probe } from '../api'
import AccountDialog from '../components/AccountDialog.vue'

/** The organization's mailboxes: mail is fetched every minute into their queues, replies go out by their servers. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const accounts = useAsyncData(() => channelsApi.accounts(tenantId.value))
const queues = useAsyncData(() => accessApi.queues(tenantId.value))

const editing = ref<EmailAccount | null>(null)
const dialogOpen = ref(false)
const deleting = ref<EmailAccount | null>(null)
const deleteOpen = ref(false)
const probes = ref<Record<string, Probe>>({})

function queueName(id: string): string {
  return queues.data.value?.find((queue) => queue.id === id)?.name ?? '–'
}

function openDialog(account: EmailAccount | null): void {
  editing.value = account
  dialogOpen.value = true
}

async function save(body: AccountRequest): Promise<void> {
  const account = editing.value
    ? await channelsApi.updateAccount(tenantId.value, editing.value.id, body)
    : await channelsApi.createAccount(tenantId.value, body)
  notify.success(
    t(editing.value ? 'channels.accounts.saved' : 'channels.accounts.created', { address: account.address }),
  )
  await accounts.reload()
}

async function test(account: EmailAccount): Promise<void> {
  try {
    const result = await channelsApi.testAccount(tenantId.value, account.id)
    probes.value = { ...probes.value, [account.id]: result }
    if (!result.imap && !result.smtp) {
      notify.success(t('channels.accounts.testOk'))
    }
  } catch (caught) {
    notify.error(caught)
  }
}

async function fetchNow(account: EmailAccount): Promise<void> {
  try {
    await channelsApi.fetchNow(tenantId.value, account.id)
    notify.success(t('channels.accounts.fetching'))
  } catch (caught) {
    notify.error(caught)
  }
}

function askDelete(account: EmailAccount): void {
  deleting.value = account
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const account = deleting.value!
  await channelsApi.deleteAccount(tenantId.value, account.id)
  notify.success(t('channels.accounts.deleted', { address: account.address }))
  await accounts.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('channels.accounts.title')" :description="$t('channels.accounts.description')">
      <Button :disabled="!queues.data.value?.length" data-test="create-account" @click="openDialog(null)">
        <Plus class="size-4" /> {{ $t('channels.accounts.create') }}
      </Button>
    </PageHeader>
    <ErrorAlert v-if="accounts.error.value" :message="accounts.error.value" />
    <EmptyState
      v-else-if="accounts.data.value?.length === 0"
      :title="$t('channels.accounts.empty')"
      :description="$t(queues.data.value?.length ? 'channels.accounts.emptyHint' : 'channels.accounts.queueFirst')"
    >
      <template #icon><Mail class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <div v-else-if="accounts.data.value" class="grid gap-4">
      <Card v-for="account in accounts.data.value" :key="account.id" :data-test="`account-${account.address}`">
        <CardHeader>
          <CardTitle class="flex flex-wrap items-center justify-between gap-2 text-base">
            <span class="flex items-center gap-2">
              {{ account.name }}
              <Badge v-if="!account.active" variant="outline">{{ $t('channels.accounts.inactive') }}</Badge>
              <Badge v-else-if="account.last_error" variant="destructive" data-test="failing">{{
                $t('channels.accounts.failing')
              }}</Badge>
            </span>
            <span class="flex gap-1">
              <Button variant="ghost" size="sm" :data-test="`test-${account.address}`" @click="test(account)"
                ><Plug class="size-4" /> {{ $t('channels.accounts.test') }}</Button
              >
              <Button variant="ghost" size="sm" :data-test="`fetch-${account.address}`" @click="fetchNow(account)"
                ><RefreshCw class="size-4" /> {{ $t('channels.accounts.fetchNow') }}</Button
              >
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.edit')"
                :data-test="`edit-${account.address}`"
                @click="openDialog(account)"
                ><Pencil class="size-4"
              /></Button>
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.delete')"
                :data-test="`delete-${account.address}`"
                @click="askDelete(account)"
                ><Trash2 class="size-4"
              /></Button>
            </span>
          </CardTitle>
          <CardDescription>
            {{ account.display_name ? `${account.display_name} <${account.address}>` : account.address }} →
            {{ queueName(account.queue_id) }}
          </CardDescription>
        </CardHeader>
        <CardContent class="grid gap-2 text-sm">
          <p class="text-muted-foreground">
            IMAP {{ account.imap.host }}:{{ account.imap.port }} · SMTP {{ account.smtp.host }}:{{ account.smtp.port }}
          </p>
          <p v-if="account.last_error" class="flex items-start gap-2 text-destructive" data-test="last-error">
            <AlertTriangle class="mt-0.5 size-4 shrink-0" />
            {{ $t('channels.accounts.failingSince', { date: formatDateTime(account.failing_since) }) }}:
            {{ account.last_error }}
          </p>
          <p v-else-if="account.last_fetch_at" class="text-xs text-muted-foreground">
            {{ $t('channels.accounts.lastFetch', { date: formatDateTime(account.last_fetch_at) }) }}
          </p>
          <div v-if="probes[account.id]" class="grid gap-1 text-xs" :data-test="`probe-${account.address}`">
            <span
              v-for="kind in ['imap', 'smtp'] as const"
              :key="kind"
              :class="probes[account.id]![kind] ? 'text-destructive' : 'text-emerald-600 dark:text-emerald-400'"
              class="flex items-center gap-1"
            >
              <AlertTriangle v-if="probes[account.id]![kind]" class="size-3.5" />
              <CheckCircle2 v-else class="size-3.5" />
              {{ kind.toUpperCase() }}: {{ probes[account.id]![kind] ?? $t('channels.accounts.works') }}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
    <AccountDialog
      v-model:open="dialogOpen"
      :title="editing ? $t('channels.accounts.edit') : $t('channels.accounts.create')"
      :initial="editing"
      :queues="queues.data.value ?? []"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('channels.accounts.deleteTitle', { address: deleting?.address })"
      :description="$t('channels.accounts.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
