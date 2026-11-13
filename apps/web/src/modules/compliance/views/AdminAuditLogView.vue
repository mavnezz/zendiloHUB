<script setup lang="ts">
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import Pager from '@/core/components/Pager.vue'
import { usePage } from '@/core/composables/use-page'
import { complianceApi } from '../api'
import AuditTable from '../components/AuditTable.vue'

const log = usePage((offset, limit) => complianceApi.platformLog({ offset, limit }))
</script>

<template>
  <div>
    <PageHeader :title="$t('audit.title')" :description="$t('audit.platformDescription')" />
    <ErrorAlert v-if="log.error.value" :message="log.error.value" />
    <template v-else>
      <AuditTable :entries="log.data.value?.items ?? []" />
      <Pager
        :label="$t('audit.count', { count: log.total.value })"
        :has-previous="log.hasPrevious.value"
        :has-next="log.hasNext.value"
        @move="log.move"
      />
    </template>
  </div>
</template>
