<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { notify } from '@/core/notify'
import { Card, CardContent } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import { accessApi, PRESETS, type Group, type Queue, type QueueRight, type RightsMatrix } from '../api'
import RightsDialog from '../components/RightsDialog.vue'

/** The rights matrix: a row per group, a column per queue, a level (or custom rights) in each cell. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)

const queues = ref<Queue[]>([])
const groups = ref<Group[]>([])
const matrix = ref<RightsMatrix | null>(null)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  try {
    const [loadedQueues, loadedGroups, loadedMatrix] = await Promise.all([
      accessApi.queues(tenantId.value),
      accessApi.groups(tenantId.value),
      accessApi.matrix(tenantId.value),
    ])
    queues.value = loadedQueues
    groups.value = loadedGroups
    matrix.value = loadedMatrix
    error.value = null
  } catch (caught) {
    notify.error(caught)
    error.value = t('common.error')
  }
}
void load()

type Level = 'none' | 'custom' | (typeof PRESETS)[number]

function rightsOf(group: Group, queue: Queue): QueueRight[] {
  return matrix.value?.grants.find((grant) => grant.group_id === group.id && grant.queue_id === queue.id)?.rights ?? []
}

function levelOf(group: Group, queue: Queue): Level {
  const grant = matrix.value?.grants.find((each) => each.group_id === group.id && each.queue_id === queue.id)
  return grant ? (grant.preset ?? 'custom') : 'none'
}

const levels = computed(() =>
  (['none', ...PRESETS, 'custom'] as Level[]).map((value) => ({ value, label: t(`access.rights.levels.${value}`) })),
)

function presetRights(level: (typeof PRESETS)[number]): QueueRight[] {
  return matrix.value?.presets[level] ?? []
}

const custom = ref<{ group: Group; queue: Queue } | null>(null)
const customOpen = ref(false)

async function setRights(group: Group, queue: Queue, rights: QueueRight[]): Promise<void> {
  try {
    await accessApi.setRights(tenantId.value, group.id, queue.id, rights)
    notify.success(t('access.rights.saved', { group: group.name, queue: queue.name }))
  } catch (caught) {
    notify.error(caught)
  }
  matrix.value = await accessApi.matrix(tenantId.value)
}

function choose(group: Group, queue: Queue, level: Level): void {
  if (level === 'custom') {
    custom.value = { group, queue }
    customOpen.value = true
    return
  }
  void setRights(group, queue, level === 'none' ? [] : presetRights(level))
}
</script>

<template>
  <div class="mx-auto grid max-w-7xl gap-6">
    <PageHeader :title="$t('access.rights.title')" :description="$t('access.rights.description')" />

    <ErrorAlert v-if="error" :message="error" />
    <EmptyState
      v-else-if="matrix && (queues.length === 0 || groups.length === 0)"
      :title="$t('access.rights.empty')"
      :description="$t('access.rights.emptyHint')"
    >
      <template #icon><span /></template>
      <div class="flex gap-4 text-sm">
        <RouterLink :to="{ name: 'queues' }" class="text-primary hover:underline">{{ $t('nav.queues') }}</RouterLink>
        <RouterLink :to="{ name: 'queueGroups' }" class="text-primary hover:underline">{{
          $t('nav.queueGroups')
        }}</RouterLink>
      </div>
    </EmptyState>
    <Card v-else-if="matrix">
      <CardContent class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('access.rights.group') }}</TableHead>
              <TableHead v-for="queue in queues" :key="queue.id" class="min-w-44">{{ queue.name }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="group in groups" :key="group.id" data-test="rights-row">
              <TableCell class="font-medium">{{ group.name }}</TableCell>
              <TableCell v-for="queue in queues" :key="queue.id">
                <NativeSelect
                  :model-value="levelOf(group, queue)"
                  :options="levels"
                  :aria-label="$t('access.rights.cell', { group: group.name, queue: queue.name })"
                  :data-test="`cell-${group.id}-${queue.id}`"
                  @update:model-value="(level: Level) => choose(group, queue, level)"
                />
                <p
                  v-if="levelOf(group, queue) === 'custom'"
                  class="mt-1 text-xs text-muted-foreground"
                  :data-test="`custom-${group.id}-${queue.id}`"
                >
                  {{
                    rightsOf(group, queue)
                      .map((right) => $t(`access.rights.names.${right}`))
                      .join(', ')
                  }}
                </p>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <div v-if="matrix" class="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2" data-test="legend">
      <p v-for="level in PRESETS" :key="level">
        <span class="font-medium text-foreground">{{ $t(`access.rights.levels.${level}`) }}:</span>
        {{
          presetRights(level)
            .map((right) => $t(`access.rights.names.${right}`))
            .join(', ')
        }}
      </p>
    </div>

    <RightsDialog
      v-if="matrix"
      v-model:open="customOpen"
      :title="$t('access.rights.cell', { group: custom?.group.name, queue: custom?.queue.name })"
      :all="matrix.rights"
      :rights="custom ? rightsOf(custom.group, custom.queue) : []"
      @save="(rights) => custom && setRights(custom.group, custom.queue, rights)"
    />
  </div>
</template>
