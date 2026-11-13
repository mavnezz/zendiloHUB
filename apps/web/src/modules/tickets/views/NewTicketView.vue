<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import SegmentedControl from '@/core/components/SegmentedControl.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import { useTenants } from '@/modules/tenancy/tenants'
import { PRIORITIES, ticketsApi, type FirstMessage, type Priority } from '../api'
import CustomerPicker from '../components/CustomerPicker.vue'
import type { PickedCustomer } from '../customer'
import { useDirectory } from '../directory'

/** A ticket written down by the team: a call, a visit, or a mail the team sends first. */
const { t } = useI18n()
const router = useRouter()
const tenants = useTenants()
const directory = useDirectory()
const tenantId = computed(() => tenants.current.value!.id)

const queueId = ref('')
const customer = ref<PickedCustomer | null>(null)
const subject = ref('')
const body = ref('')
const first = ref<FirstMessage>('customer')
const priority = ref<Priority>('normal')
const tags = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

onMounted(async () => {
  await directory.load().catch(() => undefined)
  queueId.value = directory.creatable.value[0]?.id ?? ''
})

const queueOptions = computed(() => directory.creatable.value.map((queue) => ({ value: queue.id, label: queue.name })))
const rights = computed(() => directory.creatable.value.find((queue) => queue.id === queueId.value)?.rights ?? [])
const firstOptions = computed(() =>
  (['customer', 'reply', 'note'] as const)
    .filter((each) => each === 'customer' || rights.value.includes(each))
    .map((value) => ({ value, label: t(`tickets.first.${value}`) })),
)
watch(rights, () => {
  if (!firstOptions.value.some((option) => option.value === first.value)) {
    first.value = 'customer'
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  const picked = customer.value
  try {
    const ticket = await ticketsApi.create(tenantId.value, {
      queue_id: queueId.value,
      subject: subject.value,
      body: body.value,
      first: first.value,
      priority: priority.value,
      channel: first.value === 'customer' ? 'phone' : 'web',
      tags: tags.value
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),
      customer: picked ? { id: picked.id, email: picked.email, name: picked.name ?? '', phone: picked.phone } : null,
    })
    notify.success(t('tickets.created', { number: ticket.number }))
    await router.push({ name: 'ticket', params: { tenantId: tenantId.value, ticketId: ticket.id } })
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto grid max-w-3xl gap-6">
    <PageHeader :title="$t('tickets.newTitle')" :description="$t('tickets.newText')" />
    <Card>
      <CardContent class="pt-6">
        <p v-if="queueOptions.length === 0" class="text-sm text-muted-foreground" data-test="no-queue">
          {{ $t('tickets.noQueueToCreate') }}
        </p>
        <form v-else class="grid gap-4" @submit.prevent="submit">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="grid gap-2">
              <Label for="ticket-queue">{{ $t('tickets.queue') }}</Label>
              <NativeSelect id="ticket-queue" v-model="queueId" :options="queueOptions" />
            </div>
            <div class="grid gap-2">
              <Label for="ticket-priority">{{ $t('tickets.priority') }}</Label>
              <NativeSelect
                id="ticket-priority"
                v-model="priority"
                :options="PRIORITIES.map((value) => ({ value, label: $t(`tickets.priorities.${value}`) }))"
              />
            </div>
          </div>
          <div class="grid gap-2">
            <Label for="ticket-customer">{{ $t('tickets.customer') }}</Label>
            <CustomerPicker v-model="customer" input-id="ticket-customer" />
          </div>
          <div class="grid gap-2">
            <Label for="ticket-subject">{{ $t('tickets.subject') }}</Label>
            <Input id="ticket-subject" v-model="subject" maxlength="250" required />
          </div>
          <div class="grid gap-2">
            <Label>{{ $t('tickets.firstLabel') }}</Label>
            <SegmentedControl v-model="first" :options="firstOptions" :label="$t('tickets.firstLabel')" />
          </div>
          <div class="grid gap-2">
            <Label for="ticket-body">{{ $t(`tickets.firstBody.${first}`) }}</Label>
            <Textarea id="ticket-body" v-model="body" rows="8" required />
          </div>
          <div class="grid gap-2">
            <Label for="ticket-tags">{{ $t('tickets.tags') }}</Label>
            <Input id="ticket-tags" v-model="tags" :placeholder="$t('tickets.tagsPlaceholder')" />
          </div>
          <div class="flex justify-end">
            <Button type="submit" :disabled="busy || !subject.trim() || !body.trim() || !queueId" data-test="create">
              {{ $t('tickets.create') }}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
