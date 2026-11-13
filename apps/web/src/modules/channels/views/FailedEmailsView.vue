<script setup lang="ts">
import { MailX, RotateCcw, Trash2 } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatBytes, formatDateTime } from '@/core/format'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi, type FailedEmail } from '../api'

/** Received mails that could not become tickets: process them again (e.g. after a fix) or throw them away. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const failed = useAsyncData(() => channelsApi.failed(tenantId.value))

async function retry(mail: FailedEmail): Promise<void> {
  try {
    const result = await channelsApi.retryFailed(tenantId.value, mail.id)
    if (result.outcome === 'failed') {
      notify.error(t('channels.failed.stillFailing'))
    } else {
      notify.success(t(`channels.failed.outcomes.${result.outcome}`))
    }
  } catch (caught) {
    notify.error(caught)
  }
  await failed.reload()
}

async function remove(mail: FailedEmail): Promise<void> {
  try {
    await channelsApi.deleteFailed(tenantId.value, mail.id)
    notify.success(t('channels.failed.deleted'))
  } catch (caught) {
    notify.error(caught)
  }
  await failed.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('channels.failed.title')" :description="$t('channels.failed.description')" />
    <ErrorAlert v-if="failed.error.value" :message="failed.error.value" />
    <EmptyState v-else-if="failed.data.value?.length === 0" :title="$t('channels.failed.empty')" description="">
      <template #icon><MailX class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="failed.data.value">
      <CardContent class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('channels.failed.received') }}</TableHead>
              <TableHead>{{ $t('channels.failed.mail') }}</TableHead>
              <TableHead>{{ $t('channels.failed.error') }}</TableHead>
              <TableHead class="text-right">{{ $t('common.actions') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="mail in failed.data.value" :key="mail.id" data-test="failed-email">
              <TableCell class="text-xs whitespace-nowrap">{{ formatDateTime(mail.received_at) }}</TableCell>
              <TableCell class="max-w-64">
                <span class="block truncate font-medium">{{ mail.subject || '–' }}</span>
                <span class="block truncate text-xs text-muted-foreground"
                  >{{ mail.sender || '–' }} · {{ formatBytes(mail.size) }}</span
                >
              </TableCell>
              <TableCell class="max-w-72 text-xs text-destructive">{{ mail.error }}</TableCell>
              <TableCell class="text-right whitespace-nowrap">
                <Button variant="ghost" size="sm" :data-test="`retry-${mail.id}`" @click="retry(mail)"
                  ><RotateCcw class="size-4" /> {{ $t('channels.failed.retry') }}</Button
                >
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.delete')"
                  :data-test="`delete-${mail.id}`"
                  @click="remove(mail)"
                  ><Trash2 class="size-4"
                /></Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
</template>
