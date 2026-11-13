<script setup lang="ts">
import { Check, Minus, Pencil, Plus, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { errorText } from '@/core/i18n/i18n'
import { cn } from '@/core/lib/utils'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { tenancyApi, type Permission, type Role, type RoleRequest } from '../api'
import RoleDialog from '../components/RoleDialog.vue'
import { useRoles } from '../roles'
import { useTenants } from '../tenants'

/** What each role may do: the built-in roles and the organization's own, which managers of the team can change. */
const { t } = useI18n()
const tenants = useTenants()
const roles = useRoles()
const tenant = computed(() => tenants.current.value!)
const own = computed(() => tenant.value.role)
const manage = computed(() => tenants.can('members.manage') && tenant.value.role !== null)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    await roles.load(true)
  } catch (caught) {
    error.value = errorText(caught)
  }
})

const data = computed(() => roles.data.value)

/** Permissions grouped by their area (`queues.manage` → queues), in the server's order. */
const groups = computed(() => {
  const grouped = new Map<string, Permission[]>()
  for (const permission of data.value?.permissions ?? []) {
    const area = permission.split('.')[0] as string
    grouped.set(area, [...(grouped.get(area) ?? []), permission])
  }
  return [...grouped.entries()]
})

const grantable = computed(() =>
  tenant.value.permissions.filter((permission) => !(data.value?.owner_only ?? []).includes(permission)),
)

function describe(role: Role): string {
  return role.builtin ? t(`tenant.roleDescriptions.${role.id}`) : role.description
}

const editing = ref<Role | null>(null)
const dialogOpen = ref(false)
const deleting = ref<Role | null>(null)
const deleteOpen = ref(false)

function openDialog(role: Role | null): void {
  editing.value = role
  dialogOpen.value = true
}

async function save(body: RoleRequest): Promise<void> {
  const role = editing.value
    ? await tenancyApi.updateRole(tenant.value.id, editing.value.id, body)
    : await tenancyApi.createRole(tenant.value.id, body)
  notify.success(t(editing.value ? 'roles.saved' : 'roles.created', { name: role.name }))
  await roles.load(true)
  if (editing.value && editing.value.id === own.value) {
    // The own role changed: the permissions too.
    await tenants.load(true)
  }
}

function askDelete(role: Role): void {
  deleting.value = role
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const role = deleting.value!
  await tenancyApi.deleteRole(tenant.value.id, role.id)
  notify.success(t('roles.deleted', { name: role.name }))
  await roles.load(true)
}
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <PageHeader :title="$t('roles.title')" :description="$t('roles.description')">
      <Button v-if="manage" data-test="create-role" @click="openDialog(null)">
        <Plus class="size-4" /> {{ $t('roles.create') }}
      </Button>
    </PageHeader>
    <ErrorAlert v-if="error" :message="error" />
    <template v-else-if="data">
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          v-for="role in data.roles"
          :key="role.id"
          :class="cn(role.id === own && 'border-primary')"
          :data-test="`role-card-${role.id}`"
        >
          <CardHeader>
            <CardTitle class="flex items-center justify-between gap-2 text-base">
              <span class="truncate">{{ roles.label(role.id) }}</span>
              <Badge v-if="role.builtin" variant="outline">{{ $t('roles.builtin') }}</Badge>
              <span v-else-if="manage && roles.governs(role.id)" class="flex shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.edit')"
                  :data-test="`edit-role-${role.id}`"
                  @click="openDialog(role)"
                  ><Pencil class="size-4"
                /></Button>
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.delete')"
                  :data-test="`delete-role-${role.id}`"
                  @click="askDelete(role)"
                  ><Trash2 class="size-4"
                /></Button>
              </span>
            </CardTitle>
            <CardDescription>{{ describe(role) }}</CardDescription>
            <p class="text-xs text-muted-foreground" :data-test="`role-members-${role.id}`">
              {{ $t('roles.members', role.member_count) }}
            </p>
          </CardHeader>
        </Card>
      </div>
      <Card>
        <CardContent class="overflow-x-auto pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{{ $t('roles.permission') }}</TableHead>
                <TableHead v-for="role in data.roles" :key="role.id" class="text-center">
                  {{ roles.label(role.id) }}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <template v-for="[area, permissions] in groups" :key="area">
                <TableRow class="bg-muted/40 hover:bg-muted/40">
                  <TableCell :colspan="data.roles.length + 1" class="text-xs font-medium tracking-wide uppercase">
                    {{ $t(`roles.groups.${area}`) }}
                  </TableCell>
                </TableRow>
                <TableRow v-for="permission in permissions" :key="permission" :data-test="`permission-${permission}`">
                  <TableCell>
                    {{ $t(`roles.permissions.${permission}`) }}
                    <Badge v-if="data.owner_only.includes(permission)" variant="outline" class="ml-1">
                      {{ $t('roles.ownerOnly') }}
                    </Badge>
                  </TableCell>
                  <TableCell v-for="role in data.roles" :key="role.id" class="text-center">
                    <Check
                      v-if="role.permissions.includes(permission)"
                      class="mx-auto size-4 text-primary"
                      data-test="allowed"
                    />
                    <Minus v-else class="mx-auto size-4 text-muted-foreground/50" />
                  </TableCell>
                </TableRow>
              </template>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </template>

    <RoleDialog
      v-if="data"
      v-model:open="dialogOpen"
      :title="editing ? $t('roles.editTitle', { name: editing.name }) : $t('roles.createTitle')"
      :initial="editing"
      :permissions="data.permissions"
      :grantable="grantable"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('roles.deleteTitle', { name: deleting?.name })"
      :description="$t('roles.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
