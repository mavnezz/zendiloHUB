<script setup lang="ts">
import { Pencil, Plus, Trash2, Workflow } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDateTime } from '@/core/format'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { accessApi } from '@/modules/access/api'
import { tenancyApi } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { automationApi, type Rule, type RuleKind, type RuleRequest } from '../api'
import RuleDialog from '../components/RuleDialog.vue'

/** Macros, triggers or scheduled jobs (the route says which). */
const { t } = useI18n()
const route = useRoute()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const kind = computed(() => route.meta.kind as RuleKind)
const rules = useAsyncData(() => automationApi.list(tenantId.value, kind.value))
const queues = useAsyncData(() => accessApi.queues(tenantId.value))
const members = useAsyncData(() => tenancyApi.members(tenantId.value).catch(() => []))
watch(kind, () => void rules.reload())

const editing = ref<Rule | null>(null)
const dialogOpen = ref(false)
const deleting = ref<Rule | null>(null)
const deleteOpen = ref(false)

function openDialog(rule: Rule | null): void {
  editing.value = rule
  dialogOpen.value = true
}

async function save(body: RuleRequest): Promise<void> {
  const rule = editing.value
    ? await automationApi.update(tenantId.value, kind.value, editing.value.id, body)
    : await automationApi.create(tenantId.value, kind.value, body)
  notify.success(t('automation.saved', { name: rule.name }))
  await rules.reload()
}

function describe(rule: Rule): string {
  const a = rule.actions
  const parts: string[] = []
  if (a.state) {
    parts.push(t('tickets.bulk.state', { state: t(`tickets.states.${a.state}`) }))
  }
  if (a.priority) {
    parts.push(t('tickets.bulk.priority', { priority: t(`tickets.priorities.${a.priority}`) }))
  }
  if (a.queue_id) {
    parts.push(t('tickets.bulk.queue', { queue: queues.data.value?.find((q) => q.id === a.queue_id)?.name ?? '?' }))
  }
  if (a.owner_me) {
    parts.push(t('automation.ownerMe'))
  }
  if (a.unassign) {
    parts.push(t('automation.unassign'))
  }
  for (const tag of a.add_tags ?? []) {
    parts.push(`+#${tag}`)
  }
  for (const tag of a.remove_tags ?? []) {
    parts.push(`−#${tag}`)
  }
  if (a.note) {
    parts.push(t('automation.withNote'))
  }
  if (a.reply) {
    parts.push(t('automation.withReply'))
  }
  if (a.notify_emails?.length) {
    parts.push(t('automation.withAlert', { to: a.notify_emails.join(', ') }))
  }
  return parts.join(' · ')
}

function askDelete(rule: Rule): void {
  deleting.value = rule
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const rule = deleting.value!
  await automationApi.remove(tenantId.value, kind.value, rule.id)
  notify.success(t('automation.deleted', { name: rule.name }))
  await rules.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t(`automation.${kind}.title`)" :description="$t(`automation.${kind}.description`)">
      <Button data-test="create-rule" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t(`automation.${kind}.create`) }}</Button
      >
    </PageHeader>
    <ErrorAlert v-if="rules.error.value" :message="rules.error.value" />
    <EmptyState
      v-else-if="rules.data.value?.length === 0"
      :title="$t(`automation.${kind}.empty`)"
      :description="$t(`automation.${kind}.emptyHint`)"
    >
      <template #icon><Workflow class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="rules.data.value">
      <CardContent class="grid gap-2 pt-6">
        <div
          v-for="rule in rules.data.value"
          :key="rule.id"
          class="flex items-center gap-3 rounded-md border p-3"
          :data-test="`rule-${rule.name}`"
        >
          <div class="min-w-0 flex-1">
            <p class="flex flex-wrap items-center gap-2 font-medium">
              {{ rule.name }}
              <Badge v-if="!rule.active" variant="outline">{{ $t('automation.inactive') }}</Badge>
              <Badge v-if="rule.event" variant="secondary">{{ $t(`automation.events.${rule.event}`) }}</Badge>
            </p>
            <p class="truncate text-xs text-muted-foreground">
              {{ describe(rule) }}
              <template v-if="rule.last_run_at">
                · {{ $t('automation.lastRun', { date: formatDateTime(rule.last_run_at) }) }}</template
              >
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.edit')"
            :data-test="`edit-rule-${rule.name}`"
            @click="openDialog(rule)"
            ><Pencil class="size-4"
          /></Button>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('common.delete')"
            :data-test="`delete-rule-${rule.name}`"
            @click="askDelete(rule)"
            ><Trash2 class="size-4"
          /></Button>
        </div>
      </CardContent>
    </Card>
    <RuleDialog
      v-model:open="dialogOpen"
      :kind="kind"
      :initial="editing"
      :queues="queues.data.value ?? []"
      :members="members.data.value ?? []"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('automation.deleteTitle', { name: deleting?.name })"
      :description="$t(`automation.${kind}.deleteText`)"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
