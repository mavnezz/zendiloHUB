<script setup lang="ts">
import { Mail } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDate } from '@/core/format'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useSession } from '@/modules/identity/session'
import { tenancyApi, type Invitation, type Member, type TenantRole } from '../api'
import InviteDialog from '../components/InviteDialog.vue'
import { useRoles } from '../roles'
import { useTenants } from '../tenants'

const { t } = useI18n()
const router = useRouter()
const session = useSession()
const tenants = useTenants()
/** Null for a moment after leaving or deleting the organization, until the router leaves this page. */
const current = computed(() => tenants.current.value)
const tenant = computed(() => current.value!)
const manage = computed(() => tenants.can('members.manage'))
const owner = computed(() => tenants.can('members.assign_owner'))

const roles = useRoles()
const members = useAsyncData(async () => {
  await roles.load().catch(() => undefined)
  return tenancyApi.members(tenant.value.id)
})
const invitations = useAsyncData(() =>
  manage.value ? tenancyApi.invitations(tenant.value.id) : Promise.resolve([] as Invitation[]),
)

function isMe(member: Member): boolean {
  return member.user_id === session.user.value?.id
}

/** Nobody hands out a role that may do more than they may (so only owners make owners). */
function roleOptions(member: Member) {
  const options = roles.assignable().map((role) => ({ value: role.id, label: roles.label(role.id) }))
  return options.some((option) => option.value === member.role)
    ? options
    : [{ value: member.role, label: roles.label(member.role) }, ...options]
}

/** Owners can change everyone; others only members who may not do more than they may. */
function canChange(member: Member): boolean {
  return manage.value && (owner.value || (member.role !== 'owner' && roles.governs(member.role)))
}

async function changeRole(member: Member, role: TenantRole): Promise<void> {
  try {
    const changed = await tenancyApi.changeRole(tenant.value.id, member.user_id, role)
    notify.success(t('team.roleChanged', { email: changed.email, role: roles.label(changed.role) }))
  } catch (caught) {
    notify.error(caught)
  }
  await members.reload()
  if (isMe(member)) {
    // The own role changed: the permissions too.
    await tenants.load(true)
  }
}

const removing = ref<Member | null>(null)
const removeOpen = ref(false)

function askRemove(member: Member): void {
  removing.value = member
  removeOpen.value = true
}

async function remove(): Promise<void> {
  const member = removing.value as Member
  await tenancyApi.removeMember(tenant.value.id, member.user_id)
  if (isMe(member)) {
    notify.success(t('team.left', { name: tenant.value.name }))
    tenants.forget(tenant.value.id)
    await router.push({ name: 'start' })
    return
  }
  notify.success(t('team.removed', { email: member.email }))
  await members.reload()
}

async function revoke(invitation: Invitation): Promise<void> {
  try {
    await tenancyApi.revoke(tenant.value.id, invitation.id)
    notify.success(t('team.revoked', { email: invitation.email }))
  } catch (caught) {
    notify.error(caught)
  }
  await invitations.reload()
}
</script>

<template>
  <div v-if="current" class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('team.title')" :description="$t('team.description', { name: tenant.name })">
      <InviteDialog v-if="manage" @invited="invitations.reload" />
    </PageHeader>

    <Card>
      <CardHeader>
        <CardTitle>{{ $t('team.members') }}</CardTitle>
      </CardHeader>
      <CardContent>
        <ErrorAlert v-if="members.error.value" :message="members.error.value" />
        <Table v-else>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('common.email') }}</TableHead>
              <TableHead>{{ $t('common.role') }}</TableHead>
              <TableHead class="hidden sm:table-cell">{{ $t('team.joined') }}</TableHead>
              <TableHead class="text-right">{{ $t('common.actions') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="member in members.data.value ?? []" :key="member.user_id" data-test="member">
              <TableCell class="font-medium">
                {{ member.email }}
                <Badge v-if="isMe(member)" variant="secondary" class="ml-2">{{ $t('common.you') }}</Badge>
              </TableCell>
              <TableCell>
                <NativeSelect
                  v-if="canChange(member)"
                  :model-value="member.role"
                  :options="roleOptions(member)"
                  class="w-40"
                  :data-test="`role-${member.email}`"
                  @update:model-value="(role: TenantRole) => changeRole(member, role)"
                />
                <span v-else>{{ roles.label(member.role) }}</span>
              </TableCell>
              <TableCell class="hidden text-muted-foreground sm:table-cell">{{
                formatDate(member.joined_at)
              }}</TableCell>
              <TableCell class="text-right">
                <Button v-if="isMe(member)" variant="ghost" size="sm" data-test="leave" @click="askRemove(member)">
                  {{ $t('team.leave') }}
                </Button>
                <Button
                  v-else-if="canChange(member)"
                  variant="ghost"
                  size="sm"
                  :data-test="`remove-${member.email}`"
                  @click="askRemove(member)"
                >
                  {{ $t('common.remove') }}
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <Card v-if="manage">
      <CardHeader>
        <CardTitle>{{ $t('team.invitations') }}</CardTitle>
      </CardHeader>
      <CardContent>
        <p
          v-if="!(invitations.data.value ?? []).length"
          class="text-sm text-muted-foreground"
          data-test="no-invitations"
        >
          {{ $t('team.invitationsEmpty') }}
        </p>
        <ul v-else class="divide-y">
          <li
            v-for="invitation in invitations.data.value ?? []"
            :key="invitation.id"
            class="flex flex-wrap items-center gap-3 py-3"
            data-test="invitation"
          >
            <Mail class="size-4 text-muted-foreground" />
            <span class="font-medium">{{ invitation.email }}</span>
            <Badge variant="outline">{{ roles.label(invitation.role) }}</Badge>
            <span class="text-sm text-muted-foreground">
              {{ $t('team.expires', { date: formatDate(invitation.expires_at) }) }}
            </span>
            <Button
              variant="ghost"
              size="sm"
              class="ml-auto"
              :data-test="`revoke-${invitation.email}`"
              @click="revoke(invitation)"
            >
              {{ $t('team.revoke') }}
            </Button>
          </li>
        </ul>
      </CardContent>
    </Card>

    <ConfirmDialog
      v-model:open="removeOpen"
      :title="
        removing && isMe(removing)
          ? $t('team.leaveTitle', { name: tenant.name })
          : $t('team.removeTitle', { email: removing?.email })
      "
      :description="
        removing && isMe(removing) ? $t('team.leaveText') : $t('team.removeText', { email: removing?.email })
      "
      :confirm-label="removing && isMe(removing) ? $t('team.leave') : $t('common.remove')"
      :action="remove"
    />
  </div>
</template>
