<script setup lang="ts">
import { ArrowLeft, Globe, Pencil, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/core/ui/card'
import { useTenants } from '@/modules/tenancy/tenants'
import { ticketsApi } from '@/modules/tickets/api'
import TicketTable from '@/modules/tickets/components/TicketTable.vue'
import { useDirectory } from '@/modules/tickets/directory'
import { customersApi, type CompanyRequest } from '../api'
import CompanyDialog from '../components/CompanyDialog.vue'

/** A company with its contacts and the tickets of all of them. */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const tenants = useTenants()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)
const companyId = computed(() => String(route.params.companyId))
const manage = computed(() => tenants.can('customers.manage'))

const company = useAsyncData(() => customersApi.company(tenantId.value, companyId.value))
const contacts = useAsyncData(() => customersApi.contacts(tenantId.value, { company_id: companyId.value, limit: 200 }))
const tickets = useAsyncData(async () => {
  await directory.load().catch(() => undefined)
  return ticketsApi.list(tenantId.value, { view: 'all', company_id: companyId.value, limit: 100 })
})
const editOpen = ref(false)
const deleteOpen = ref(false)

async function save(body: CompanyRequest): Promise<void> {
  const saved = await customersApi.updateCompany(tenantId.value, companyId.value, body)
  notify.success(t('customers.companies.saved', { name: saved.name }))
  await company.reload()
}

async function remove(): Promise<void> {
  await customersApi.deleteCompany(tenantId.value, companyId.value)
  notify.success(t('customers.companies.deleted', { name: company.data.value?.name }))
  await router.push({ name: 'companies', params: { tenantId: tenantId.value } })
}
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <RouterLink
      :to="{ name: 'companies', params: { tenantId } }"
      class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      ><ArrowLeft class="size-4" /> {{ $t('customers.companies.back') }}</RouterLink
    >
    <ErrorAlert v-if="company.error.value" :message="company.error.value" />
    <template v-else-if="company.data.value">
      <Card>
        <CardHeader>
          <CardTitle class="flex flex-wrap items-center justify-between gap-2">
            <span data-test="company-name">{{ company.data.value.name }}</span>
            <span v-if="manage" class="flex gap-2">
              <Button variant="outline" size="sm" data-test="edit-company" @click="editOpen = true"
                ><Pencil class="size-4" /> {{ $t('common.edit') }}</Button
              >
              <Button variant="outline" size="sm" data-test="delete-company" @click="deleteOpen = true"
                ><Trash2 class="size-4" /> {{ $t('common.delete') }}</Button
              >
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent class="grid gap-2 text-sm">
          <span v-if="company.data.value.domain" class="flex items-center gap-2"
            ><Globe class="size-4 text-muted-foreground" />{{ company.data.value.domain }}</span
          >
          <p v-if="company.data.value.notes" class="whitespace-pre-wrap text-muted-foreground">
            {{ company.data.value.notes }}
          </p>
          <div v-if="contacts.data.value?.items.length" class="flex flex-wrap gap-2 pt-2" data-test="company-contacts">
            <RouterLink
              v-for="contact in contacts.data.value.items"
              :key="contact.id"
              :to="{ name: 'contact', params: { tenantId, contactId: contact.id } }"
              class="rounded-md border px-2 py-1 text-xs hover:bg-muted"
              >{{ contact.name }}</RouterLink
            >
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle class="text-base">{{
            $t('customers.tickets', { count: tickets.data.value?.total ?? 0 })
          }}</CardTitle>
        </CardHeader>
        <CardContent class="overflow-x-auto">
          <p v-if="tickets.data.value?.items.length === 0" class="text-sm text-muted-foreground">
            {{ $t('customers.noTickets') }}
          </p>
          <TicketTable v-else-if="tickets.data.value" :tickets="tickets.data.value.items" />
        </CardContent>
      </Card>
    </template>
    <CompanyDialog
      v-model:open="editOpen"
      :title="$t('customers.companies.edit')"
      :initial="company.data.value"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('customers.companies.deleteTitle', { name: company.data.value?.name })"
      :description="$t('customers.companies.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
