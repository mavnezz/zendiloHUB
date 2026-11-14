<script setup lang="ts">
import { Sparkles } from '@lucide/vue'
import { ref, watch } from 'vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { useTenants } from '@/modules/tenancy/tenants'
import { ticketsApi } from '../api'
import { useAssistant } from '../assistant'

/** The AI assistant's summary of the ticket, on request (only when the server has one). */
const props = defineProps<{ ticketId: string }>()
const tenants = useTenants()
const enabled = useAssistant(tenants.current.value!.id)
const summary = ref<string | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

async function summarize(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    summary.value = (await ticketsApi.assist(tenants.current.value!.id, props.ticketId, 'summary')).text
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
watch(
  () => props.ticketId,
  () => {
    summary.value = null
    error.value = null
  },
)
</script>

<template>
  <section v-if="enabled" class="grid gap-2 rounded-lg border p-3 text-sm" data-test="assist">
    <h3 class="flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
      <Sparkles class="size-3.5" /> {{ $t('tickets.assist.title') }}
    </h3>
    <p v-if="summary" class="whitespace-pre-wrap" data-test="assist-summary">{{ summary }}</p>
    <p v-if="error" class="text-destructive" data-test="assist-error">{{ error }}</p>
    <Button variant="outline" size="sm" :disabled="busy" data-test="summarize" @click="summarize">
      {{ busy ? $t('tickets.assist.working') : summary ? $t('tickets.assist.again') : $t('tickets.assist.summarize') }}
    </Button>
    <p class="text-xs text-muted-foreground">{{ $t('tickets.assist.hint') }}</p>
  </section>
</template>
