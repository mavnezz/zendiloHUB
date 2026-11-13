<script setup lang="ts">
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import Pager from '@/core/components/Pager.vue'
import { usePage } from '@/core/composables/use-page'
import { Card, CardContent } from '@/core/ui/card'
import { useTenants } from '@/modules/tenancy/tenants'
import { complianceApi } from '../api'
import AuditTable from '../components/AuditTable.vue'

const tenants = useTenants()
const tenantId = tenants.current.value?.id ?? ''
const log = usePage((offset, limit) => complianceApi.tenantLog(tenantId, { offset, limit }))
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <PageHeader :title="$t('audit.title')" :description="$t('audit.description')" />
    <ErrorAlert v-if="log.error.value" :message="log.error.value" />
    <Card v-else>
      <CardContent class="pt-6">
        <AuditTable :entries="log.data.value?.items ?? []" />
        <Pager
          :label="$t('audit.count', { count: log.total.value })"
          :has-previous="log.hasPrevious.value"
          :has-next="log.hasNext.value"
          @move="log.move"
        />
      </CardContent>
    </Card>
  </div>
</template>
