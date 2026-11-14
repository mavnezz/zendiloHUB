<script setup lang="ts">
import { refDebounced } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDate } from '@/core/format'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { identityApi, type User } from '../api'
import { useSession } from '../session'

const PAGE_SIZE = 50

/** Other modules add a column through the `extra` slots and learn which users are shown from `loaded`. */
const emit = defineEmits<{ loaded: [users: User[]] }>()

const { t } = useI18n()
const session = useSession()
const search = ref('')
const query = refDebounced(search, 250)
const offset = ref(0)
const { data, error, reload } = useAsyncData(() =>
  identityApi.users({ q: query.value, offset: offset.value, limit: PAGE_SIZE }),
)
watch(data, (page) => emit('loaded', page?.items ?? []))
watch(query, () => {
  offset.value = 0
  void reload()
})
const total = computed(() => data.value?.total ?? 0)

function page(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  void reload()
}

async function toggleRole(user: User): Promise<void> {
  try {
    await identityApi.changeRole(user.id, user.role === 'admin' ? 'user' : 'admin')
    notify.success(t('admin.roleChanged', { email: user.email }))
    await reload()
  } catch (caught) {
    notify.error(caught)
  }
}

const deleting = ref<User | null>(null)
const deleteOpen = ref(false)

function askDelete(user: User): void {
  deleting.value = user
  deleteOpen.value = true
}

const resetting = ref<User | null>(null)
const resetOpen = ref(false)

function askReset(user: User): void {
  resetting.value = user
  resetOpen.value = true
}

async function resetTwoFactor(): Promise<void> {
  const user = resetting.value as User
  await identityApi.resetTwoFactor(user.id)
  notify.success(t('admin.twoFactorReset', { email: user.email }))
  await reload()
}

async function deleteUser(): Promise<void> {
  const user = deleting.value as User
  await identityApi.deleteUser(user.id)
  notify.success(t('admin.deleted', { email: user.email }))
  await reload()
}
</script>

<template>
  <div>
    <PageHeader :title="$t('admin.users')" :description="$t('admin.usersDescription')">
      <Input
        v-model="search"
        type="search"
        class="w-64"
        :placeholder="$t('admin.searchPlaceholder')"
        :aria-label="$t('common.search')"
        data-test="search"
      />
    </PageHeader>
    <ErrorAlert v-if="error" :message="error" />
    <div v-else class="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ $t('admin.email') }}</TableHead>
            <TableHead>{{ $t('admin.role') }}</TableHead>
            <TableHead>{{ $t('admin.registered') }}</TableHead>
            <TableHead v-if="$slots.extra"><slot name="extra-head" /></TableHead>
            <TableHead class="text-right" />
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="user in data?.items ?? []" :key="user.id" data-test="user-row">
            <TableCell class="font-medium">
              {{ user.email }}
              <span v-if="user.id === session.user.value?.id" class="text-muted-foreground"
                >({{ $t('admin.you') }})</span
              >
            </TableCell>
            <TableCell>
              <Badge :variant="user.role === 'admin' ? 'default' : 'secondary'">{{
                $t(`admin.roles.${user.role}`)
              }}</Badge>
              <Badge v-if="user.two_factor" variant="outline" class="ml-1" data-test="two-factor-badge">{{
                $t('admin.twoFactor')
              }}</Badge>
            </TableCell>
            <TableCell>{{ formatDate(user.created_at) }}</TableCell>
            <TableCell v-if="$slots.extra"><slot name="extra" :user="user" /></TableCell>
            <TableCell class="text-right whitespace-nowrap">
              <template v-if="user.id !== session.user.value?.id">
                <Button variant="ghost" size="sm" data-test="toggle-role" @click="toggleRole(user)">
                  {{ user.role === 'admin' ? $t('admin.makeUser') : $t('admin.makeAdmin') }}
                </Button>
                <Button
                  v-if="user.two_factor"
                  variant="ghost"
                  size="sm"
                  data-test="reset-two-factor"
                  @click="askReset(user)"
                >
                  {{ $t('admin.resetTwoFactor') }}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  class="text-destructive"
                  data-test="delete-user"
                  @click="askDelete(user)"
                >
                  {{ $t('common.delete') }}
                </Button>
              </template>
            </TableCell>
          </TableRow>
          <TableRow v-if="data && data.items.length === 0">
            <TableCell :colspan="$slots.extra ? 5 : 4" class="py-8 text-center text-muted-foreground">{{
              $t('admin.noUsers')
            }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <div class="mt-4 flex items-center justify-between text-sm text-muted-foreground">
      <span data-test="user-count">{{ $t('admin.count', { count: total }) }}</span>
      <div class="flex gap-2">
        <Button variant="outline" size="sm" :disabled="offset === 0" data-test="previous" @click="page(-1)">
          {{ $t('common.previous') }}
        </Button>
        <Button variant="outline" size="sm" :disabled="offset + PAGE_SIZE >= total" data-test="next" @click="page(1)">
          {{ $t('common.next') }}
        </Button>
      </div>
    </div>

    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('admin.deleteTitle', { email: deleting?.email ?? '' })"
      :description="$t('admin.deleteText')"
      :confirm-label="$t('common.delete')"
      :action="deleteUser"
    />
    <ConfirmDialog
      v-model:open="resetOpen"
      :title="$t('admin.resetTwoFactorTitle', { email: resetting?.email ?? '' })"
      :description="$t('admin.resetTwoFactorText')"
      :confirm-label="$t('admin.resetTwoFactor')"
      :action="resetTwoFactor"
    />
  </div>
</template>
