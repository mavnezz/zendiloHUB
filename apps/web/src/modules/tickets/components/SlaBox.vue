<script setup lang="ts">
import { AlarmClock } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useNow } from '@/core/composables/use-now'
import { formatDateTime } from '@/core/format'
import { cn } from '@/core/lib/utils'
import { serviceApi, type TicketClock } from '@/modules/service/api'
import { useTenants } from '@/modules/tenancy/tenants'

/** The ticket's service level deadlines: met, still open, or missed. */
const props = defineProps<{ ticketId: string; updatedAt: string }>()

const tenants = useTenants()
const clock = ref<TicketClock | null>(null)
const now = useNow(30_000)

async function load(): Promise<void> {
  clock.value = await serviceApi.clock(tenants.current.value!.id, props.ticketId).catch(() => null)
}
onMounted(load)
watch(() => props.updatedAt, load)

const rows = computed(() => {
  const found = clock.value
  if (!found) {
    return []
  }
  return (
    [
      ['firstResponse', found.first_response_due, found.first_responded_at, 'first_response'],
      ['solution', found.solution_due, found.solved_at, 'solution'],
    ] as const
  )
    .filter(([, due]) => due)
    .map(([key, due, met, kind]) => ({
      key,
      due: due!,
      met,
      late: !met && (found.breached.includes(kind) || new Date(due!).getTime() <= now.value),
    }))
})
</script>

<template>
  <section v-if="rows.length" class="grid gap-1.5 rounded-lg border p-3 text-sm" data-test="sla">
    <h3 class="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
      <AlarmClock class="size-3.5" /> {{ $t('service.title') }}
    </h3>
    <p
      v-for="row in rows"
      :key="row.key"
      :class="cn('flex justify-between gap-2', row.late && 'font-medium text-destructive')"
      :data-test="`sla-${row.key}`"
    >
      <span>{{ $t(`service.${row.key}`) }}</span>
      <span v-if="row.met" class="text-emerald-600 dark:text-emerald-400">{{ $t('service.met') }}</span>
      <span v-else>{{ row.late ? $t('service.missed') : formatDateTime(row.due) }}</span>
    </p>
  </section>
</template>
