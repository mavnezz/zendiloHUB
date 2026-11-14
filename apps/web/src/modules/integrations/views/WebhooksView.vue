<script setup lang="ts">
import { Copy, Pencil, Plus, Send, Trash2, Webhook as WebhookIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDateTime } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import { useTenants } from '@/modules/tenancy/tenants'
import { integrationsApi, WEBHOOK_EVENTS, type Webhook, type WebhookDelivery, type WebhookEvent } from '../api'

/** Other systems that hear about tickets: each event is POSTed as JSON, signed with the webhook's secret. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const webhooks = useAsyncData(() => integrationsApi.list(tenantId.value))

const editing = ref<Webhook | null>(null)
const dialogOpen = ref(false)
const form = ref({ name: '', url: '', events: [] as WebhookEvent[], active: true, new_secret: false })
const error = ref<string | null>(null)
const secret = ref<string | null>(null)
const deliveries = ref<WebhookDelivery[] | null>(null)
const deliveriesOf = ref<Webhook | null>(null)
const deleting = ref<Webhook | null>(null)
const deleteOpen = ref(false)

function openDialog(webhook: Webhook | null): void {
  editing.value = webhook
  form.value = {
    name: webhook?.name ?? '',
    url: webhook?.url ?? 'https://',
    events: [...(webhook?.events ?? ['ticket.created'])],
    active: webhook?.active ?? true,
    new_secret: false,
  }
  error.value = null
  dialogOpen.value = true
}

function toggle(event: WebhookEvent, on: boolean): void {
  form.value.events = on ? [...form.value.events, event] : form.value.events.filter((each) => each !== event)
}

async function save(): Promise<void> {
  error.value = null
  try {
    const saved = editing.value
      ? await integrationsApi.update(tenantId.value, editing.value.id, form.value)
      : await integrationsApi.create(tenantId.value, form.value)
    dialogOpen.value = false
    secret.value = saved.secret ?? null
    notify.success(t('webhooks.saved', { name: saved.name }))
    await webhooks.reload()
  } catch (caught) {
    error.value = errorText(caught)
  }
}

async function copySecret(): Promise<void> {
  await navigator.clipboard?.writeText(secret.value ?? '')
  notify.success(t('webhooks.copied'))
}

async function test(webhook: Webhook): Promise<void> {
  try {
    await integrationsApi.test(tenantId.value, webhook.id)
    notify.success(t('webhooks.testSent'))
  } catch (caught) {
    notify.error(caught)
  }
}

async function showDeliveries(webhook: Webhook): Promise<void> {
  deliveriesOf.value = webhook
  deliveries.value = await integrationsApi.deliveries(tenantId.value, webhook.id).catch(() => [])
}

function askDelete(webhook: Webhook): void {
  deleting.value = webhook
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  await integrationsApi.remove(tenantId.value, deleting.value!.id)
  notify.success(t('webhooks.deleted', { name: deleting.value!.name }))
  await webhooks.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('webhooks.title')" :description="$t('webhooks.description')">
      <Button data-test="create-webhook" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('webhooks.create') }}</Button
      >
    </PageHeader>
    <ErrorAlert v-if="webhooks.error.value" :message="webhooks.error.value" />
    <EmptyState
      v-else-if="webhooks.data.value?.length === 0"
      :title="$t('webhooks.empty')"
      :description="$t('webhooks.emptyHint')"
    >
      <template #icon><WebhookIcon class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="webhooks.data.value">
      <CardContent class="grid gap-2 pt-6">
        <div
          v-for="webhook in webhooks.data.value"
          :key="webhook.id"
          class="flex items-center gap-3 rounded-md border p-3"
          :data-test="`webhook-${webhook.name}`"
        >
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-2 font-medium">
              {{ webhook.name }}
              <Badge v-if="!webhook.active" variant="outline">{{ $t('automation.inactive') }}</Badge>
              <Badge v-if="webhook.last_error" variant="destructive">{{ webhook.last_error }}</Badge>
            </p>
            <p class="truncate text-xs text-muted-foreground">{{ webhook.url }} · {{ webhook.events.join(', ') }}</p>
          </div>
          <Button variant="ghost" size="sm" :data-test="`test-${webhook.name}`" @click="test(webhook)"
            ><Send class="size-4" /> {{ $t('webhooks.test') }}</Button
          >
          <Button
            variant="ghost"
            size="sm"
            :data-test="`deliveries-${webhook.name}`"
            @click="showDeliveries(webhook)"
            >{{ $t('webhooks.deliveries') }}</Button
          >
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.edit')"
            :data-test="`edit-${webhook.name}`"
            @click="openDialog(webhook)"
            ><Pencil class="size-4"
          /></Button>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.delete')"
            :data-test="`delete-${webhook.name}`"
            @click="askDelete(webhook)"
            ><Trash2 class="size-4"
          /></Button>
        </div>
      </CardContent>
    </Card>

    <Card v-if="secret" class="border-primary" data-test="secret">
      <CardContent class="grid gap-2 pt-6 text-sm">
        <p>{{ $t('webhooks.secretText') }}</p>
        <div class="flex gap-2">
          <code class="flex-1 truncate rounded bg-muted px-2 py-1.5">{{ secret }}</code>
          <Button variant="outline" size="sm" data-test="copy-secret" @click="copySecret"
            ><Copy class="size-4" /> {{ $t('webhooks.copy') }}</Button
          >
        </div>
        <p class="text-xs text-muted-foreground">{{ $t('webhooks.verify') }}</p>
      </CardContent>
    </Card>

    <Card v-if="deliveries && deliveriesOf" data-test="delivery-list">
      <CardContent class="grid gap-1 pt-6 text-sm">
        <p class="mb-2 font-medium">{{ $t('webhooks.deliveriesOf', { name: deliveriesOf.name }) }}</p>
        <p v-if="!deliveries.length" class="text-muted-foreground">{{ $t('webhooks.noDeliveries') }}</p>
        <p v-for="delivery in deliveries" :key="delivery.id" class="flex justify-between gap-2 text-xs">
          <span
            >{{ formatDateTime(delivery.created_at) }} · {{ delivery.event }} ·
            {{ $t('webhooks.attempt', { count: delivery.attempt }) }}</span
          >
          <span :class="delivery.error ? 'text-destructive' : 'text-emerald-600 dark:text-emerald-400'">{{
            delivery.error ?? delivery.status
          }}</span>
        </p>
      </CardContent>
    </Card>

    <Dialog v-model:open="dialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ editing ? $t('webhooks.edit') : $t('webhooks.create') }}</DialogTitle>
          <DialogDescription>{{ $t('webhooks.dialogText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="save">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-2">
            <Label for="webhook-name">{{ $t('automation.name') }}</Label>
            <Input id="webhook-name" v-model="form.name" maxlength="80" required autofocus />
          </div>
          <div class="grid gap-2">
            <Label for="webhook-url">URL</Label>
            <Input id="webhook-url" v-model="form.url" type="url" maxlength="2000" required />
          </div>
          <div class="grid gap-2 text-sm">
            <label
              v-for="event in WEBHOOK_EVENTS"
              :key="event"
              class="flex items-center gap-2"
              :data-test="`event-${event}`"
            >
              <Checkbox
                :model-value="form.events.includes(event)"
                @update:model-value="(on) => toggle(event, on === true)"
              />
              <code class="text-xs">{{ event }}</code> {{ $t(`webhooks.events.${event.replace('.', '_')}`) }}
            </label>
          </div>
          <label class="flex items-center gap-3 text-sm"
            ><Switch v-model="form.active" /> {{ $t('automation.active') }}</label
          >
          <label v-if="editing" class="flex items-center gap-3 text-sm"
            ><Switch v-model="form.new_secret" data-test="new-secret" /> {{ $t('webhooks.newSecret') }}</label
          >
          <DialogFooter>
            <Button type="submit" :disabled="!form.events.length" data-test="save-webhook">{{
              $t('common.save')
            }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('webhooks.deleteTitle', { name: deleting?.name })"
      :description="$t('webhooks.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
