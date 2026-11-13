<script setup lang="ts">
import { UserPlus, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { customersApi, type Contact } from '@/modules/customers/api'
import { useTenants } from '@/modules/tenancy/tenants'

import type { PickedCustomer } from '../customer'

/** Who a ticket is about: a contact found by name, e-mail or phone, or a new one by e-mail address or phone. */
const model = defineModel<PickedCustomer | null>({ default: null })
defineProps<{ inputId?: string }>()

const tenants = useTenants()
const text = ref('')
const found = ref<Contact[]>([])
let timer: ReturnType<typeof setTimeout> | undefined

const canSearch = computed(() => tenants.can('customers.view'))
const looksLikeEmail = computed(() => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text.value.trim()))
const looksLikePhone = computed(() => /^\+?[0-9 ()./-]{5,}$/.test(text.value.trim()))

async function search(): Promise<void> {
  const tenant = tenants.current.value
  const query = text.value.trim()
  if (!tenant || !canSearch.value || query.length < 2) {
    found.value = []
    return
  }
  try {
    found.value = (await customersApi.contacts(tenant.id, { q: query, limit: 8 })).items
  } catch {
    found.value = []
  }
}

watch(text, () => {
  clearTimeout(timer)
  timer = setTimeout(() => void search(), 250)
})

function pick(contact: Contact): void {
  model.value = { id: contact.id, label: contact.email ? `${contact.name} <${contact.email}>` : contact.name }
  text.value = ''
  found.value = []
}

function pickNew(): void {
  const value = text.value.trim()
  model.value = looksLikeEmail.value ? { email: value, label: value } : { phone: value, label: value }
  text.value = ''
  found.value = []
}

/** For tests: search at once instead of after typing stops. */
defineExpose({ search })
</script>

<template>
  <div class="relative grid gap-1">
    <div
      v-if="model"
      class="flex items-center justify-between rounded-md border px-3 py-1.5 text-sm"
      data-test="picked"
    >
      <span class="truncate">{{ model.label }}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        class="size-6"
        :aria-label="$t('common.remove')"
        data-test="unpick"
        @click="model = null"
        ><X class="size-3.5"
      /></Button>
    </div>
    <template v-else>
      <Input
        :id="inputId"
        v-model="text"
        :placeholder="$t('tickets.customerPlaceholder')"
        data-test="customer-search"
      />
      <div
        v-if="found.length || looksLikeEmail || looksLikePhone"
        class="absolute top-10 z-20 grid w-full gap-0.5 rounded-md border bg-popover p-1 shadow-md"
      >
        <button
          v-for="contact in found"
          :key="contact.id"
          type="button"
          class="rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
          :data-test="`contact-${contact.id}`"
          @click="pick(contact)"
        >
          {{ contact.name }}
          <span class="text-xs text-muted-foreground">{{ contact.email ?? contact.phone }}</span>
          <span v-if="contact.company" class="text-xs text-muted-foreground"> · {{ contact.company.name }}</span>
        </button>
        <button
          v-if="(looksLikeEmail || looksLikePhone) && !found.some((each) => each.email === text.trim().toLowerCase())"
          type="button"
          class="flex items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
          data-test="new-customer"
          @click="pickNew"
        >
          <UserPlus class="size-4" /> {{ $t('tickets.newCustomer', { value: text.trim() }) }}
        </button>
      </div>
    </template>
  </div>
</template>
