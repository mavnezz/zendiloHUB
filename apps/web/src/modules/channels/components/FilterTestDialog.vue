<script setup lang="ts">
import { ArrowRight, Ban, CheckCircle2 } from '@lucide/vue'
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import type { Queue } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi, type EmailAccount, type FilterTest } from '../api'

/** Pastes an e-mail (its source) and shows its way: the filters that match, in order, and the queue it lands in. */
const props = defineProps<{
  accounts: EmailAccount[]
  queues: Queue[]
  /** The mailbox to start with; null: the first one. */
  start?: string | null
}>()
const open = defineModel<boolean>('open', { default: false })

const tenants = useTenants()
const raw = ref('')
const accountId = ref('')
const result = ref<FilterTest | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    accountId.value = props.start ?? props.accounts[0]?.id ?? ''
    result.value = null
    error.value = null
  }
})

function queueName(id: string | null): string {
  return props.queues.find((queue) => queue.id === id)?.name ?? '–'
}

function scopeName(id: string | null): string {
  return props.accounts.find((account) => account.id === id)?.address ?? ''
}

async function run(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    result.value = await channelsApi.testFilters(tenants.current.value!.id, raw.value, accountId.value || null)
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ $t('channels.filters.test.title') }}</DialogTitle>
        <DialogDescription>{{ $t('channels.filters.test.text') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="run">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="test-account">{{ $t('channels.filters.test.mailbox') }}</Label>
          <NativeSelect
            id="test-account"
            v-model="accountId"
            :options="[
              { value: '', label: $t('channels.filters.test.noMailbox') },
              ...accounts.map((account) => ({ value: account.id, label: account.address })),
            ]"
          />
        </div>
        <div class="grid gap-2">
          <Label for="test-raw">{{ $t('channels.filters.test.source') }}</Label>
          <Textarea
            id="test-raw"
            v-model="raw"
            rows="8"
            class="font-mono text-xs"
            maxlength="1000000"
            required
            data-test="test-raw"
            placeholder="From: carl@customer.example&#10;To: support@acme.example&#10;Subject: Invoice 42&#10;&#10;…"
          />
        </div>
        <Button type="submit" class="justify-self-start" :disabled="busy || !raw.trim()" data-test="run-test">{{
          $t('channels.filters.test.run')
        }}</Button>
      </form>
      <div v-if="result" class="grid gap-2 rounded-md border p-3 text-sm" data-test="test-result">
        <p class="text-xs text-muted-foreground">
          {{ $t('channels.filters.test.checked', { count: result.checked }) }}
        </p>
        <ol v-if="result.matched.length" class="grid gap-1">
          <li v-for="found in result.matched" :key="found.id" class="flex items-center gap-2">
            <CheckCircle2 class="size-4 text-emerald-600 dark:text-emerald-400" />
            {{ found.name }}
            <span class="text-xs text-muted-foreground">{{
              found.account_id
                ? $t('channels.filters.ruleOf', { address: scopeName(found.account_id) })
                : $t('channels.filters.everyMailbox')
            }}</span>
          </li>
        </ol>
        <p v-else class="text-muted-foreground">{{ $t('channels.filters.test.none') }}</p>
        <p v-if="result.stopped && !result.ignore" class="text-xs text-muted-foreground">
          {{ $t('channels.filters.test.stopped') }}
        </p>
        <p v-if="result.ignore" class="flex items-center gap-2 font-medium text-destructive" data-test="test-dropped">
          <Ban class="size-4" /> {{ $t('channels.filters.test.dropped') }}
        </p>
        <p v-else class="flex items-center gap-2 font-medium" data-test="test-queue">
          <ArrowRight class="size-4" />
          {{
            result.final_queue_id
              ? $t(result.queue_id ? 'channels.filters.test.byFilter' : 'channels.filters.test.byDefault', {
                  queue: queueName(result.final_queue_id),
                })
              : $t('channels.filters.test.noQueue')
          }}
        </p>
        <p v-if="!result.ignore && (result.priority || result.tags.length)" class="text-xs text-muted-foreground">
          <span v-if="result.priority">{{ $t(`tickets.priorities.${result.priority}`) }}</span>
          <span v-for="tag in result.tags" :key="tag"> #{{ tag }}</span>
        </p>
      </div>
    </DialogContent>
  </Dialog>
</template>
