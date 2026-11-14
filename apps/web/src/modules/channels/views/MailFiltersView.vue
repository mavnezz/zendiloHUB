<script setup lang="ts">
import { Filter, FlaskConical, Plus } from '@lucide/vue'
import { computed, ref } from 'vue'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { accessApi } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi } from '../api'
import FilterDialog from '../components/FilterDialog.vue'
import FilterList from '../components/FilterList.vue'
import FilterTestDialog from '../components/FilterTestDialog.vue'
import { useFilterEditor } from '../filter-editor'

/**
 * Rules for incoming mail (like OTOBO's postmaster filters): those for all mailboxes run first, then the rules of the
 * mailbox that received the mail, each from top to bottom.
 */
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const filters = useAsyncData(() => channelsApi.filters(tenantId.value))
const queues = useAsyncData(() => accessApi.queues(tenantId.value))
const accounts = useAsyncData(() => channelsApi.accounts(tenantId.value))
const editor = useFilterEditor(tenantId, () => filters.reload())
const testOpen = ref(false)

const everyMailbox = computed(() => (filters.data.value ?? []).filter((each) => each.account_id === null))
const mailboxes = computed(() =>
  (accounts.data.value ?? [])
    .map((account) => ({
      account,
      rules: (filters.data.value ?? []).filter((each) => each.account_id === account.id),
    }))
    .filter((each) => each.rules.length),
)
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('channels.filters.title')" :description="$t('channels.filters.description')">
      <Button variant="outline" data-test="test-filters" @click="testOpen = true"
        ><FlaskConical class="size-4" /> {{ $t('channels.filters.test.open') }}</Button
      >
      <Button data-test="create-filter" @click="editor.open(null)"
        ><Plus class="size-4" /> {{ $t('channels.filters.create') }}</Button
      >
    </PageHeader>
    <ErrorAlert v-if="filters.error.value" :message="filters.error.value" />
    <EmptyState
      v-else-if="filters.data.value?.length === 0"
      :title="$t('channels.filters.empty')"
      :description="$t('channels.filters.emptyHint')"
    >
      <template #icon><Filter class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <template v-else-if="filters.data.value">
      <Card v-if="everyMailbox.length" data-test="scope-all">
        <CardHeader>
          <CardTitle class="text-base">{{ $t('channels.filters.everyMailbox') }}</CardTitle>
          <CardDescription>{{ $t('channels.filters.everyMailboxHint') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <FilterList
            :filters="everyMailbox"
            :queues="queues.data.value ?? []"
            @edit="editor.open($event)"
            @delete="editor.askDelete($event)"
            @reorder="editor.reorder($event, null)"
          />
        </CardContent>
      </Card>
      <Card v-for="{ account, rules } in mailboxes" :key="account.id" :data-test="`scope-${account.address}`">
        <CardHeader>
          <CardTitle class="text-base">{{ $t('channels.filters.ruleOf', { address: account.address }) }}</CardTitle>
          <CardDescription>{{ $t('channels.filters.mailboxHint') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <FilterList
            :filters="rules"
            :queues="queues.data.value ?? []"
            numbered
            @edit="editor.open($event)"
            @delete="editor.askDelete($event)"
            @reorder="editor.reorder($event, account.id)"
          />
        </CardContent>
      </Card>
    </template>
    <FilterDialog
      v-model:open="editor.dialogOpen.value"
      :initial="editor.editing.value"
      :scope="editor.scope.value"
      :queues="queues.data.value ?? []"
      :accounts="accounts.data.value ?? []"
      :save="editor.save"
    />
    <FilterTestDialog v-model:open="testOpen" :accounts="accounts.data.value ?? []" :queues="queues.data.value ?? []" />
    <ConfirmDialog
      v-model:open="editor.deleteOpen.value"
      :title="$t('channels.filters.deleteTitle', { name: editor.deleting.value?.name })"
      :description="$t('channels.filters.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="editor.remove"
    />
  </div>
</template>
