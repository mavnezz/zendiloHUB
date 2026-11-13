<script setup lang="ts">
import { refDebounced } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDate } from '@/core/format'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { tenancyApi, type Tenant } from '../api'

const PAGE_SIZE = 50

const { t } = useI18n()
const search = ref('')
const query = refDebounced(search, 250)
const offset = ref(0)
const { data, error, reload } = useAsyncData(() =>
  tenancyApi.adminTenants({ q: query.value, offset: offset.value, limit: PAGE_SIZE }),
)
watch(query, () => {
  offset.value = 0
  void reload()
})
const total = computed(() => data.value?.total ?? 0)

function page(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  void reload()
}

async function toggle(tenant: Tenant): Promise<void> {
  const status = tenant.status === 'active' ? 'suspended' : 'active'
  try {
    await tenancyApi.changeStatus(tenant.id, status)
    notify.success(t(status === 'active' ? 'admin.reactivated' : 'admin.suspended', { name: tenant.name }))
    await reload()
  } catch (caught) {
    notify.error(caught)
  }
}
</script>

<template>
  <div>
    <PageHeader :title="$t('admin.tenants')" :description="$t('admin.tenantsDescription')">
      <Input
        v-model="search"
        type="search"
        class="w-64"
        :placeholder="$t('admin.searchTenants')"
        :aria-label="$t('common.search')"
        data-test="search"
      />
    </PageHeader>
    <ErrorAlert v-if="error" :message="error" />
    <template v-else>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ $t('common.name') }}</TableHead>
            <TableHead>{{ $t('common.status') }}</TableHead>
            <TableHead>{{ $t('admin.members') }}</TableHead>
            <TableHead>{{ $t('admin.created') }}</TableHead>
            <TableHead class="text-right">{{ $t('common.actions') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="tenant in data?.items ?? []" :key="tenant.id" data-test="tenant">
            <TableCell class="font-medium">{{ tenant.name }}</TableCell>
            <TableCell>
              <Badge :variant="tenant.status === 'active' ? 'secondary' : 'destructive'">
                {{ $t(`admin.statuses.${tenant.status}`) }}
              </Badge>
            </TableCell>
            <TableCell>{{ tenant.member_count }}</TableCell>
            <TableCell class="text-muted-foreground">{{ formatDate(tenant.created_at) }}</TableCell>
            <TableCell class="text-right">
              <Button variant="ghost" size="sm" :data-test="`toggle-${tenant.name}`" @click="toggle(tenant)">
                {{ tenant.status === 'active' ? $t('admin.suspend') : $t('admin.reactivate') }}
              </Button>
            </TableCell>
          </TableRow>
          <TableRow v-if="data && !data.items.length">
            <TableCell colspan="5" class="py-8 text-center text-muted-foreground">{{
              $t('admin.noTenants')
            }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <div class="mt-4 flex items-center justify-between text-sm text-muted-foreground">
        <span data-test="count">{{ $t('admin.tenantCount', { count: total }) }}</span>
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="offset === 0" data-test="previous" @click="page(-1)">
            {{ $t('common.previous') }}
          </Button>
          <Button variant="outline" size="sm" :disabled="offset + PAGE_SIZE >= total" data-test="next" @click="page(1)">
            {{ $t('common.next') }}
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
