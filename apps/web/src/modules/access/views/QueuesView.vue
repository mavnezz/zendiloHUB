<script setup lang="ts">
import { Inbox, Pencil, Plus, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import { accessApi, type Queue } from '../api'
import NameDialog from '../components/NameDialog.vue'

/** The queues of the organization: where tickets will live. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const queues = useAsyncData(() => accessApi.queues(tenantId.value))

const editing = ref<Queue | null>(null)
const dialogOpen = ref(false)
const deleting = ref<Queue | null>(null)
const deleteOpen = ref(false)

function openDialog(queue: Queue | null): void {
  editing.value = queue
  dialogOpen.value = true
}

async function save(body: { name: string; description: string }): Promise<void> {
  const queue = editing.value
    ? await accessApi.updateQueue(tenantId.value, editing.value.id, body)
    : await accessApi.createQueue(tenantId.value, body)
  notify.success(t(editing.value ? 'access.queues.saved' : 'access.queues.created', { name: queue.name }))
  await queues.reload()
}

function askDelete(queue: Queue): void {
  deleting.value = queue
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const queue = deleting.value!
  await accessApi.deleteQueue(tenantId.value, queue.id)
  notify.success(t('access.queues.deleted', { name: queue.name }))
  await queues.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('access.queues.title')" :description="$t('access.queues.description')">
      <Button data-test="create-queue" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('access.queues.create') }}</Button
      >
    </PageHeader>

    <ErrorAlert v-if="queues.error.value" :message="queues.error.value" />
    <EmptyState
      v-else-if="queues.data.value?.length === 0"
      :title="$t('access.queues.empty')"
      :description="$t('access.queues.emptyHint')"
    >
      <template #icon><Inbox class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="queues.data.value">
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('access.name') }}</TableHead>
              <TableHead class="hidden sm:table-cell">{{ $t('access.descriptionLabel') }}</TableHead>
              <TableHead class="text-right">{{ $t('common.actions') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="queue in queues.data.value" :key="queue.id" data-test="queue">
              <TableCell class="font-medium">{{ queue.name }}</TableCell>
              <TableCell class="hidden text-muted-foreground sm:table-cell">{{ queue.description }}</TableCell>
              <TableCell class="text-right">
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('access.queues.edit')"
                  :data-test="`edit-queue-${queue.id}`"
                  @click="openDialog(queue)"
                >
                  <Pencil class="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.delete')"
                  :data-test="`delete-queue-${queue.id}`"
                  @click="askDelete(queue)"
                >
                  <Trash2 class="size-4" />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <NameDialog
      v-model:open="dialogOpen"
      :title="$t(editing ? 'access.queues.edit' : 'access.queues.create')"
      :description="$t('access.queues.dialogText')"
      :initial="editing"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('access.queues.deleteTitle', { name: deleting?.name })"
      :description="$t('access.queues.deleteText')"
      :confirm-label="$t('common.delete')"
      :action="remove"
    />
  </div>
</template>
