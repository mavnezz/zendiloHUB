<script setup lang="ts">
import { Plus, Search, Users } from '@lucide/vue'
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
import { customersApi, type ContactRequest } from '../api'
import ContactDialog from '../components/ContactDialog.vue'

/** Everyone who wrote in (or was written down), searchable by name, e-mail address and phone number. */
const { t } = useI18n()
const router = useRouter()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const manage = computed(() => tenants.can('customers.manage'))
const search = ref('')
const page = usePage((offset, limit) => customersApi.contacts(tenantId.value, { q: search.value, offset, limit }))
const companies = ref<{ id: string; name: string }[]>([])
const dialogOpen = ref(false)

async function openDialog(): Promise<void> {
  companies.value = (await customersApi.companies(tenantId.value, { limit: 200 }).catch(() => ({ items: [] }))).items
  dialogOpen.value = true
}

async function create(body: ContactRequest): Promise<void> {
  const contact = await customersApi.createContact(tenantId.value, body)
  notify.success(t('customers.contacts.created', { name: contact.name }))
  await router.push({ name: 'contact', params: { tenantId: tenantId.value, contactId: contact.id } })
}

function find(): void {
  page.offset.value = 0
  void page.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('customers.contacts.title')" :description="$t('customers.contacts.description')">
      <Button v-if="manage" data-test="create-contact" @click="openDialog"
        ><Plus class="size-4" /> {{ $t('customers.contacts.create') }}</Button
      >
    </PageHeader>
    <form class="relative" @submit.prevent="find">
      <Search class="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
      <Input
        v-model="search"
        type="search"
        class="pl-8"
        :placeholder="$t('customers.contacts.search')"
        data-test="search"
      />
    </form>
    <ErrorAlert v-if="page.error.value" :message="page.error.value" />
    <EmptyState
      v-else-if="page.data.value?.items.length === 0"
      :title="$t('customers.contacts.empty')"
      :description="$t('customers.contacts.emptyHint')"
    >
      <template #icon><Users class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="page.data.value">
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('customers.name') }}</TableHead>
              <TableHead>{{ $t('customers.email') }}</TableHead>
              <TableHead class="hidden md:table-cell">{{ $t('customers.phone') }}</TableHead>
              <TableHead class="hidden sm:table-cell">{{ $t('customers.company') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="contact in page.data.value.items" :key="contact.id" data-test="contact">
              <TableCell>
                <RouterLink
                  :to="{ name: 'contact', params: { tenantId, contactId: contact.id } }"
                  class="font-medium hover:underline"
                  >{{ contact.name }}</RouterLink
                >
              </TableCell>
              <TableCell>{{ contact.email ?? '–' }}</TableCell>
              <TableCell class="hidden md:table-cell">{{ contact.phone ?? '–' }}</TableCell>
              <TableCell class="hidden sm:table-cell">
                <RouterLink
                  v-if="contact.company"
                  :to="{ name: 'company', params: { tenantId, companyId: contact.company.id } }"
                  class="hover:underline"
                  >{{ contact.company.name }}</RouterLink
                >
                <span v-else class="text-muted-foreground">–</span>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
        <Pager
          :label="$t('customers.contacts.count', { count: page.total.value })"
          :has-previous="page.hasPrevious.value"
          :has-next="page.hasNext.value"
          @move="page.move"
        />
      </CardContent>
    </Card>
    <ContactDialog
      v-model:open="dialogOpen"
      :title="$t('customers.contacts.create')"
      :initial="null"
      :companies="companies"
      :save="create"
    />
  </div>
</template>
