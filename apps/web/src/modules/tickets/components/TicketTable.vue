<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { formatDateTime } from '@/core/format'
import { Checkbox } from '@/core/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import type { Ticket } from '../api'
import { useDirectory } from '../directory'
import PriorityBadge from './PriorityBadge.vue'
import StateBadge from './StateBadge.vue'

/** A list of tickets; with `selectable`, rows can be picked for bulk changes (`selected` holds their ids). */
const props = defineProps<{ tickets: Ticket[]; selectable?: boolean; hideCustomer?: boolean }>()
const selected = defineModel<string[]>('selected', { default: () => [] })

const tenants = useTenants()
const directory = useDirectory()
const allSelected = computed(() => props.tickets.length > 0 && selected.value.length === props.tickets.length)

function toggle(id: string, on: boolean): void {
  selected.value = on ? [...new Set([...selected.value, id])] : selected.value.filter((each) => each !== id)
}

function toggleAll(on: boolean): void {
  selected.value = on ? props.tickets.map((ticket) => ticket.id) : []
}
</script>

<template>
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead v-if="selectable" class="w-8">
          <Checkbox
            :model-value="allSelected"
            :aria-label="$t('tickets.selectAll')"
            data-test="select-all"
            @update:model-value="(on) => toggleAll(on === true)"
          />
        </TableHead>
        <TableHead class="w-20">#</TableHead>
        <TableHead>{{ $t('tickets.subject') }}</TableHead>
        <TableHead v-if="!hideCustomer" class="hidden md:table-cell">{{ $t('tickets.customer') }}</TableHead>
        <TableHead class="hidden lg:table-cell">{{ $t('tickets.queue') }}</TableHead>
        <TableHead>{{ $t('tickets.state') }}</TableHead>
        <TableHead class="hidden sm:table-cell">{{ $t('tickets.priority') }}</TableHead>
        <TableHead class="hidden xl:table-cell">{{ $t('tickets.owner') }}</TableHead>
        <TableHead class="hidden lg:table-cell">{{ $t('tickets.updated') }}</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      <TableRow v-for="ticket in tickets" :key="ticket.id" data-test="ticket-row">
        <TableCell v-if="selectable">
          <Checkbox
            :model-value="selected.includes(ticket.id)"
            :aria-label="$t('tickets.select', { number: ticket.number })"
            :data-test="`select-${ticket.number}`"
            @update:model-value="(on) => toggle(ticket.id, on === true)"
          />
        </TableCell>
        <TableCell class="font-mono text-xs text-muted-foreground">{{ ticket.number }}</TableCell>
        <TableCell class="max-w-0 min-w-48">
          <RouterLink
            :to="{ name: 'ticket', params: { tenantId: tenants.current.value?.id, ticketId: ticket.id } }"
            class="block truncate font-medium hover:underline"
            :data-test="`ticket-${ticket.number}`"
            >{{ ticket.subject }}</RouterLink
          >
          <span v-if="ticket.tags.length" class="block truncate text-xs text-muted-foreground">
            {{ ticket.tags.map((tag) => `#${tag}`).join(' ') }}
          </span>
        </TableCell>
        <TableCell v-if="!hideCustomer" class="hidden max-w-48 truncate md:table-cell">
          <template v-if="ticket.customer">
            {{ ticket.customer.name }}
            <span v-if="ticket.customer.company_name" class="block truncate text-xs text-muted-foreground">
              {{ ticket.customer.company_name }}
            </span>
          </template>
          <span v-else class="text-muted-foreground">–</span>
        </TableCell>
        <TableCell class="hidden lg:table-cell">{{ directory.queueName(ticket.queue_id) }}</TableCell>
        <TableCell><StateBadge :state="ticket.state" /></TableCell>
        <TableCell class="hidden sm:table-cell"><PriorityBadge :priority="ticket.priority" /></TableCell>
        <TableCell class="hidden max-w-40 truncate xl:table-cell">{{
          directory.memberName(ticket.owner_id)
        }}</TableCell>
        <TableCell class="hidden text-xs whitespace-nowrap text-muted-foreground lg:table-cell">
          {{ formatDateTime(ticket.updated_at) }}
        </TableCell>
      </TableRow>
    </TableBody>
  </Table>
</template>
