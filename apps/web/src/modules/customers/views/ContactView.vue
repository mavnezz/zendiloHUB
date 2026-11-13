<script setup lang="ts">
import { ArrowLeft, Building2, Mail, Pencil, Phone, Plus, Trash2 } from '@lucide/vue'
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
import { customersApi, type ContactRequest } from '../api'
import ContactDialog from '../components/ContactDialog.vue'

/** A contact with their details and all their tickets (the customer's history, like OTOBO's information center). */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const tenants = useTenants()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)
const contactId = computed(() => String(route.params.contactId))
const manage = computed(() => tenants.can('customers.manage'))

const contact = useAsyncData(() => customersApi.contact(tenantId.value, contactId.value))
const tickets = useAsyncData(async () => {
  await directory.load().catch(() => undefined)
  return ticketsApi.list(tenantId.value, { view: 'all', customer_id: contactId.value, limit: 100 })
})
const companies = ref<{ id: string; name: string }[]>([])
const editOpen = ref(false)
const deleteOpen = ref(false)

async function openEdit(): Promise<void> {
  companies.value = (await customersApi.companies(tenantId.value, { limit: 200 }).catch(() => ({ items: [] }))).items
  editOpen.value = true
}

async function save(body: ContactRequest): Promise<void> {
  const saved = await customersApi.updateContact(tenantId.value, contactId.value, body)
  notify.success(t('customers.contacts.saved', { name: saved.name }))
  await contact.reload()
}

async function remove(): Promise<void> {
  await customersApi.deleteContact(tenantId.value, contactId.value)
  notify.success(t('customers.contacts.deleted', { name: contact.data.value?.name }))
  await router.push({ name: 'contacts', params: { tenantId: tenantId.value } })
}
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <RouterLink
      :to="{ name: 'contacts', params: { tenantId } }"
      class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      ><ArrowLeft class="size-4" /> {{ $t('customers.contacts.back') }}</RouterLink
    >
    <ErrorAlert v-if="contact.error.value" :message="contact.error.value" />
    <template v-else-if="contact.data.value">
      <Card>
        <CardHeader>
          <CardTitle class="flex flex-wrap items-center justify-between gap-2">
            <span data-test="contact-name">{{ contact.data.value.name }}</span>
            <span v-if="manage" class="flex gap-2">
              <Button variant="outline" size="sm" data-test="edit-contact" @click="openEdit"
                ><Pencil class="size-4" /> {{ $t('common.edit') }}</Button
              >
              <Button variant="outline" size="sm" data-test="delete-contact" @click="deleteOpen = true"
                ><Trash2 class="size-4" /> {{ $t('common.delete') }}</Button
              >
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent class="grid gap-2 text-sm">
          <span v-if="contact.data.value.email" class="flex items-center gap-2"
            ><Mail class="size-4 text-muted-foreground" />{{ contact.data.value.email }}</span
          >
          <span v-if="contact.data.value.phone" class="flex items-center gap-2"
            ><Phone class="size-4 text-muted-foreground" />{{ contact.data.value.phone }}</span
          >
          <RouterLink
            v-if="contact.data.value.company"
            :to="{ name: 'company', params: { tenantId, companyId: contact.data.value.company.id } }"
            class="flex items-center gap-2 hover:underline"
            ><Building2 class="size-4 text-muted-foreground" />{{ contact.data.value.company.name }}</RouterLink
          >
          <p v-if="contact.data.value.notes" class="whitespace-pre-wrap text-muted-foreground">
            {{ contact.data.value.notes }}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center justify-between text-base">
            {{ $t('customers.tickets', { count: tickets.data.value?.total ?? 0 }) }}
            <Button v-if="directory.creatable.value.length" variant="outline" size="sm" as-child>
              <RouterLink :to="{ name: 'newTicket', params: { tenantId } }"
                ><Plus class="size-4" /> {{ $t('tickets.new') }}</RouterLink
              >
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent class="overflow-x-auto">
          <ErrorAlert v-if="tickets.error.value" :message="tickets.error.value" />
          <p v-else-if="tickets.data.value?.items.length === 0" class="text-sm text-muted-foreground">
            {{ $t('customers.noTickets') }}
          </p>
          <TicketTable v-else-if="tickets.data.value" :tickets="tickets.data.value.items" hide-customer />
        </CardContent>
      </Card>
    </template>
    <ContactDialog
      v-model:open="editOpen"
      :title="$t('customers.contacts.edit')"
      :initial="contact.data.value"
      :companies="companies"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('customers.contacts.deleteTitle', { name: contact.data.value?.name })"
      :description="$t('customers.contacts.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
