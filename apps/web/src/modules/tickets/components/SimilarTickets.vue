<script setup lang="ts">
import { Copy } from '@lucide/vue'
import { onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useTenants } from '@/modules/tenancy/tenants'
import { ticketsApi, type Ticket } from '../api'

/** Tickets about the same thing: the same problem of other customers, or a duplicate to merge. */
const props = defineProps<{ ticketId: string }>()
const tenants = useTenants()
const tickets = ref<Ticket[]>([])

async function load(): Promise<void> {
  const found = await ticketsApi.similar(tenants.current.value!.id, props.ticketId).catch(() => null)
  tickets.value = found?.items ?? []
}
onMounted(load)
watch(() => props.ticketId, load)
</script>

<template>
  <section v-if="tickets.length" class="grid gap-1.5 rounded-lg border p-3 text-sm" data-test="similar">
    <h3 class="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
      <Copy class="size-3.5" /> {{ $t('tickets.similar') }}
    </h3>
    <RouterLink
      v-for="each in tickets"
      :key="each.id"
      :to="{ name: 'ticket', params: { tenantId: tenants.current.value!.id, ticketId: each.id } }"
      class="flex gap-2 hover:underline"
      :data-test="`similar-${each.id}`"
    >
      <span class="text-muted-foreground tabular-nums">#{{ each.number }}</span>
      <span class="truncate">{{ each.subject }}</span>
      <span class="ml-auto shrink-0 text-xs text-muted-foreground">{{ $t(`tickets.states.${each.state}`) }}</span>
    </RouterLink>
  </section>
</template>
