<script setup lang="ts">
import { Check } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import PageHeader from '@/core/components/PageHeader.vue'
import { cn } from '@/core/lib/utils'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { tenancyApi } from '@/modules/tenancy/api'
import { useTenants } from '@/modules/tenancy/tenants'

/** The start page of an organization: the first steps; queues and tickets join it with their phases. */
const tenants = useTenants()
const tenant = computed(() => tenants.current.value)

const DISMISSED_KEY = 'zendilohub.setup-dismissed'
const dismissed = ref(readDismissed())
const teamDone = ref(false)

function readDismissed(): boolean {
  try {
    return localStorage.getItem(`${DISMISSED_KEY}.${tenant.value?.id}`) === '1'
  } catch {
    return false
  }
}

// The checklist is a hint: a list it may not see or cannot load just leaves its step open.
if (tenant.value && tenants.can('members.view')) {
  tenancyApi
    .members(tenant.value.id)
    .then((members) => (teamDone.value = members.length > 1))
    .catch(() => undefined)
}

const steps = computed(() => [
  { key: 'settings', route: tenants.can('tenant.manage') ? 'settings' : null, done: false },
  { key: 'team', route: tenants.can('members.view') ? 'team' : null, done: teamDone.value },
])
const done = computed(() => steps.value.filter((step) => step.done).length)

function dismiss(): void {
  dismissed.value = true
  try {
    localStorage.setItem(`${DISMISSED_KEY}.${tenant.value?.id}`, '1')
  } catch {
    // Without storage the checklist comes back on the next visit; nothing else depends on it.
  }
}
</script>

<template>
  <div class="mx-auto grid max-w-7xl gap-6">
    <PageHeader :title="$t('overview.title')" :description="$t('overview.description', { name: tenant?.name })" />

    <Card v-if="!dismissed" data-test="setup">
      <CardHeader class="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{{ $t('overview.setup.title') }}</CardTitle>
          <CardDescription data-test="setup-progress">
            {{ $t('overview.setup.progress', { done, total: steps.length }) }}
          </CardDescription>
        </div>
        <Button variant="ghost" size="sm" data-test="setup-dismiss" @click="dismiss">
          {{ $t('overview.setup.dismiss') }}
        </Button>
      </CardHeader>
      <CardContent class="grid gap-3 sm:grid-cols-2">
        <component
          :is="step.route ? RouterLink : 'div'"
          v-for="(step, index) in steps"
          :key="step.key"
          :to="step.route ? { name: step.route } : undefined"
          :data-test="`step-${step.key}`"
          :class="
            cn(
              'rounded-lg border p-3 transition-colors',
              step.route && 'hover:border-primary/50 hover:bg-muted/40',
              step.done && 'border-primary/40 bg-primary/5',
            )
          "
        >
          <div class="flex items-center gap-2">
            <span
              :class="
                cn(
                  'flex size-6 shrink-0 items-center justify-center rounded-full border text-xs',
                  step.done && 'border-primary bg-primary text-primary-foreground',
                )
              "
            >
              <Check v-if="step.done" class="size-3.5" />
              <template v-else>{{ index + 1 }}</template>
            </span>
            <span class="text-sm font-medium">{{ $t(`overview.setup.${step.key}`) }}</span>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">{{ $t(`overview.setup.${step.key}Text`) }}</p>
        </component>
      </CardContent>
    </Card>
  </div>
</template>
