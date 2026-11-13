<script setup lang="ts">
import { Pencil, Plus, Trash2, Users } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { tenancyApi, type Member } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { accessApi, type Group } from '../api'
import MembersDialog from '../components/MembersDialog.vue'
import NameDialog from '../components/NameDialog.vue'

/** The groups of the organization: people who work together and get rights in queues. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const groups = useAsyncData(() => accessApi.groups(tenantId.value))
const members = useAsyncData(() => tenancyApi.members(tenantId.value))

const emails = computed(
  () => new Map((members.data.value ?? []).map((member: Member) => [member.user_id, member.email])),
)

function memberNames(group: Group): string[] {
  return group.member_ids.map((id) => emails.value.get(id) ?? id).sort()
}

const editing = ref<Group | null>(null)
const dialogOpen = ref(false)
const membersOpen = ref(false)
const deleting = ref<Group | null>(null)
const deleteOpen = ref(false)

function openDialog(group: Group | null): void {
  editing.value = group
  dialogOpen.value = true
}

function openMembers(group: Group): void {
  editing.value = group
  membersOpen.value = true
}

async function save(body: { name: string; description: string }): Promise<void> {
  const group = editing.value
    ? await accessApi.updateGroup(tenantId.value, editing.value.id, body)
    : await accessApi.createGroup(tenantId.value, body)
  notify.success(t(editing.value ? 'access.groups.saved' : 'access.groups.created', { name: group.name }))
  await groups.reload()
}

async function membersSaved(group: Group): Promise<void> {
  notify.success(t('access.groups.membersSaved', { name: group.name }))
  await groups.reload()
}

function askDelete(group: Group): void {
  deleting.value = group
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const group = deleting.value!
  await accessApi.deleteGroup(tenantId.value, group.id)
  notify.success(t('access.groups.deleted', { name: group.name }))
  await groups.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('access.groups.title')" :description="$t('access.groups.description')">
      <Button data-test="create-group" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('access.groups.create') }}</Button
      >
    </PageHeader>

    <ErrorAlert v-if="groups.error.value" :message="groups.error.value" />
    <EmptyState
      v-else-if="groups.data.value?.length === 0"
      :title="$t('access.groups.empty')"
      :description="$t('access.groups.emptyHint')"
    >
      <template #icon><Users class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="groups.data.value">
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('access.name') }}</TableHead>
              <TableHead>{{ $t('access.groups.members') }}</TableHead>
              <TableHead class="text-right">{{ $t('common.actions') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="group in groups.data.value" :key="group.id" data-test="group">
              <TableCell class="font-medium">
                {{ group.name }}
                <p v-if="group.description" class="text-xs font-normal text-muted-foreground">
                  {{ group.description }}
                </p>
              </TableCell>
              <TableCell>
                <div class="flex flex-wrap gap-1" :data-test="`members-${group.id}`">
                  <Badge v-for="name in memberNames(group)" :key="name" variant="secondary">{{ name }}</Badge>
                  <span v-if="group.member_ids.length === 0" class="text-sm text-muted-foreground">
                    {{ $t('access.groups.nobody') }}
                  </span>
                </div>
              </TableCell>
              <TableCell class="text-right whitespace-nowrap">
                <Button variant="outline" size="sm" :data-test="`edit-members-${group.id}`" @click="openMembers(group)">
                  <Users class="size-4" /> {{ $t('access.groups.editMembers') }}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('access.groups.edit')"
                  :data-test="`edit-group-${group.id}`"
                  @click="openDialog(group)"
                >
                  <Pencil class="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.delete')"
                  :data-test="`delete-group-${group.id}`"
                  @click="askDelete(group)"
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
      :title="$t(editing ? 'access.groups.edit' : 'access.groups.create')"
      :description="$t('access.groups.dialogText')"
      :initial="editing"
      :save="save"
    />
    <MembersDialog
      v-model:open="membersOpen"
      :tenant-id="tenantId"
      :group="editing"
      :members="members.data.value ?? []"
      @saved="membersSaved"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('access.groups.deleteTitle', { name: deleting?.name })"
      :description="$t('access.groups.deleteText')"
      :confirm-label="$t('common.delete')"
      :action="remove"
    />
  </div>
</template>
