<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import SegmentedControl from '@/core/components/SegmentedControl.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { Card, CardContent, CardHeader, CardTitle } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import { useDirectory } from '@/modules/tickets/directory'
import { reportingApi, type ReportGroup } from '../api'
import DailyChart from '../components/DailyChart.vue'

/** Key figures of the tickets: how many came and went, how fast the team answered and solved, where the load is. */
const { t } = useI18n()
const tenants = useTenants()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)
const days = ref<7 | 30 | 90>(30)
const queueId = ref('')
const showTable = ref(false)

function iso(date: Date): string {
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const report = useAsyncData(async () => {
  await directory.load().catch(() => undefined)
  const end = new Date()
  const start = new Date(end.getTime() - (days.value - 1) * 86_400_000)
  return reportingApi.report(tenantId.value, {
    start: iso(start),
    end: iso(end),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    queue_id: queueId.value || undefined,
  })
})
watch([days, queueId], () => void report.reload())

function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) {
    return '–'
  }
  if (minutes < 60) {
    return t('reports.minutes', { count: Math.round(minutes) })
  }
  if (minutes < 60 * 24) {
    return t('reports.hours', { count: Math.round(minutes / 6) / 10 })
  }
  return t('reports.days', { count: Math.round(minutes / 144) / 10 })
}

function owner(group: ReportGroup): string {
  return group.key ? directory.memberName(group.key) : t('tickets.nobody')
}

const tiles = computed(() => {
  const found = report.data.value
  if (!found) {
    return []
  }
  return [
    { key: 'created', value: String(found.created) },
    { key: 'closed', value: String(found.closed) },
    {
      key: 'openNow',
      value: String(found.open_now),
      hint: t('reports.unassignedNow', { count: found.unassigned_now }),
    },
    { key: 'firstResponse', value: duration(found.first_response_median) },
    { key: 'resolution', value: duration(found.resolution_median) },
    { key: 'breached', value: String(found.breached), hint: t('reports.reopened', { count: found.reopened }) },
  ]
})
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <PageHeader :title="$t('reports.title')" :description="$t('reports.description')" />
    <div class="flex flex-wrap items-center gap-2">
      <SegmentedControl
        v-model="days"
        :label="$t('reports.period')"
        :options="([7, 30, 90] as const).map((value) => ({ value, label: $t('reports.lastDays', { count: value }) }))"
      />
      <NativeSelect
        v-model="queueId"
        class="w-48"
        :aria-label="$t('tickets.queue')"
        :options="[
          { value: '', label: $t('tickets.allQueues') },
          ...directory.queues.value.map((queue) => ({ value: queue.id, label: queue.name })),
        ]"
      />
    </div>
    <ErrorAlert v-if="report.error.value" :message="report.error.value" />
    <template v-else-if="report.data.value">
      <div class="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Card v-for="tile in tiles" :key="tile.key" :data-test="`tile-${tile.key}`">
          <CardContent class="grid gap-1 pt-6">
            <span class="text-xs text-muted-foreground">{{ $t(`reports.tiles.${tile.key}`) }}</span>
            <span class="text-2xl font-semibold tabular-nums">{{ tile.value }}</span>
            <span v-if="tile.hint" class="text-xs text-muted-foreground">{{ tile.hint }}</span>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center justify-between text-base">
            {{ $t('reports.perDay') }}
            <button
              type="button"
              class="text-xs font-normal underline"
              data-test="toggle-table"
              @click="showTable = !showTable"
            >
              {{ showTable ? $t('reports.showChart') : $t('reports.showTable') }}
            </button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table v-if="showTable" data-test="day-table">
            <TableHeader>
              <TableRow>
                <TableHead>{{ $t('reports.day') }}</TableHead>
                <TableHead class="text-right">{{ $t('reports.opened') }}</TableHead>
                <TableHead class="text-right">{{ $t('reports.closed') }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="day in report.data.value.days" :key="day.day">
                <TableCell>{{ day.day }}</TableCell>
                <TableCell class="text-right tabular-nums">{{ day.created }}</TableCell>
                <TableCell class="text-right tabular-nums">{{ day.closed }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <DailyChart v-else :days="report.data.value.days" />
        </CardContent>
      </Card>
      <div class="grid gap-4 lg:grid-cols-3">
        <Card
          v-for="[key, groups] in [
            ['queues', report.data.value.queues],
            ['owners', report.data.value.owners],
            ['channels', report.data.value.channels],
          ] as const"
          :key="key"
          :data-test="`groups-${key}`"
        >
          <CardHeader>
            <CardTitle class="text-base">{{ $t(`reports.by.${key}`) }}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead />
                  <TableHead class="text-right">{{ $t('reports.opened') }}</TableHead>
                  <TableHead class="text-right">{{ $t('reports.closed') }}</TableHead>
                  <TableHead class="text-right">{{ $t('reports.open') }}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="group in groups" :key="String(group.key)">
                  <TableCell class="max-w-40 truncate">{{
                    key === 'queues'
                      ? directory.queueName(group.key)
                      : key === 'owners'
                        ? owner(group)
                        : $t(`reports.channels.${group.key}`)
                  }}</TableCell>
                  <TableCell class="text-right tabular-nums">{{ group.created }}</TableCell>
                  <TableCell class="text-right tabular-nums">{{ group.closed }}</TableCell>
                  <TableCell class="text-right tabular-nums">{{ group.open }}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <p v-if="!groups.length" class="text-sm text-muted-foreground">{{ $t('reports.none') }}</p>
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>
