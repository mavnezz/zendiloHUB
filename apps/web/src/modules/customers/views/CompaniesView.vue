<script setup lang="ts">
import { Building2, Plus, Search } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import Pager from '@/core/components/Pager.vue'
import { usePage } from '@/core/composables/use-page'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import { customersApi, type CompanyRequest } from '../api'
import CompanyDialog from '../components/CompanyDialog.vue'

/** The customers' companies; new contacts with a company's domain join it on their own. */
const { t } = useI18n()
const router = useRouter()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const manage = computed(() => tenants.can('customers.manage'))
const search = ref('')
const page = usePage((offset, limit) => customersApi.companies(tenantId.value, { q: search.value, offset, limit }))
const dialogOpen = ref(false)

async function create(body: CompanyRequest): Promise<void> {
  const company = await customersApi.createCompany(tenantId.value, body)
  notify.success(t('customers.companies.created', { name: company.name }))
  await router.push({ name: 'company', params: { tenantId: tenantId.value, companyId: company.id } })
}

function find(): void {
  page.offset.value = 0
  void page.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('customers.companies.title')" :description="$t('customers.companies.description')">
      <Button v-if="manage" data-test="create-company" @click="dialogOpen = true"
        ><Plus class="size-4" /> {{ $t('customers.companies.create') }}</Button
      >
    </PageHeader>
    <form class="relative" @submit.prevent="find">
      <Search class="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
      <Input
        v-model="search"
        type="search"
        class="pl-8"
        :placeholder="$t('customers.companies.search')"
        data-test="search"
      />
    </form>
    <ErrorAlert v-if="page.error.value" :message="page.error.value" />
    <EmptyState
      v-else-if="page.data.value?.items.length === 0"
      :title="$t('customers.companies.empty')"
      :description="$t('customers.companies.emptyHint')"
    >
      <template #icon><Building2 class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="page.data.value">
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('customers.name') }}</TableHead>
              <TableHead>{{ $t('customers.domain') }}</TableHead>
              <TableHead class="text-right">{{ $t('customers.companies.contacts') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="company in page.data.value.items" :key="company.id" data-test="company">
              <TableCell>
                <RouterLink
                  :to="{ name: 'company', params: { tenantId, companyId: company.id } }"
                  class="font-medium hover:underline"
                  >{{ company.name }}</RouterLink
                >
              </TableCell>
              <TableCell>{{ company.domain ?? '–' }}</TableCell>
              <TableCell class="text-right">{{ company.contact_count }}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
        <Pager
          :label="$t('customers.companies.count', { count: page.total.value })"
          :has-previous="page.hasPrevious.value"
          :has-next="page.hasNext.value"
          @move="page.move"
        />
      </CardContent>
    </Card>
    <CompanyDialog v-model:open="dialogOpen" :title="$t('customers.companies.create')" :initial="null" :save="create" />
  </div>
</template>
