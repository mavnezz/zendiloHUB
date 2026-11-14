<script setup lang="ts">
import { Copy, ExternalLink } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import { accessApi, type Queue } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { portalApi } from '../api'

/** Switching the customer portal on: where its tickets go and whether colleagues see each other's tickets. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const enabled = ref(false)
const queueId = ref('')
const companyTickets = ref(false)
const queues = ref<Queue[]>([])
const error = ref<string | null>(null)
const busy = ref(false)
const address = computed(() => `${window.location.origin}/portal/${tenantId.value}`)
const queueOptions = computed(() => [
  { value: '', label: t('portal.settings.chooseQueue') },
  ...queues.value.map((queue) => ({ value: queue.id, label: queue.name })),
])

onMounted(async () => {
  try {
    const [settings, listed] = await Promise.all([portalApi.settings(tenantId.value), accessApi.queues(tenantId.value)])
    queues.value = listed
    enabled.value = settings.enabled ?? false
    queueId.value = settings.queue_id ?? ''
    companyTickets.value = settings.company_tickets ?? false
  } catch (caught) {
    error.value = errorText(caught)
  }
})

async function save(): Promise<void> {
  error.value = null
  busy.value = true
  try {
    await portalApi.saveSettings(tenantId.value, {
      enabled: enabled.value,
      queue_id: queueId.value || null,
      company_tickets: companyTickets.value,
    })
    notify.success(t('portal.settings.saved'))
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}

async function copy(): Promise<void> {
  await navigator.clipboard?.writeText(address.value)
  notify.success(t('webhooks.copied'))
}
</script>

<template>
  <div class="mx-auto grid max-w-3xl gap-6">
    <PageHeader :title="$t('portal.settings.title')" :description="$t('portal.settings.description')" />
    <Card>
      <CardContent class="grid gap-4 pt-6">
        <ErrorAlert v-if="error" :message="error" />
        <form class="grid gap-4" @submit.prevent="save">
          <label class="flex items-center gap-2 text-sm font-medium">
            <Switch v-model="enabled" data-test="portal-enabled" /> {{ $t('portal.settings.enabled') }}
          </label>
          <div class="grid gap-1.5">
            <Label for="portal-queue">{{ $t('portal.settings.queue') }}</Label>
            <NativeSelect id="portal-queue" v-model="queueId" :options="queueOptions" data-test="portal-queue" />
            <p class="text-xs text-muted-foreground">{{ $t('portal.settings.queueHint') }}</p>
          </div>
          <label class="flex items-start gap-2 text-sm">
            <Switch v-model="companyTickets" data-test="portal-company" />
            <span>
              <span class="font-medium">{{ $t('portal.settings.companyTickets') }}</span>
              <span class="block text-xs text-muted-foreground">{{ $t('portal.settings.companyHint') }}</span>
            </span>
          </label>
          <Button type="submit" class="justify-self-start" :disabled="busy" data-test="portal-save">{{
            $t('common.save')
          }}</Button>
        </form>
        <div class="grid gap-1.5 border-t pt-4">
          <Label for="portal-address">{{ $t('portal.settings.address') }}</Label>
          <div class="flex gap-2">
            <Input id="portal-address" :model-value="address" readonly data-test="portal-address" />
            <Button variant="outline" size="icon" :aria-label="$t('webhooks.copy')" @click="copy"
              ><Copy class="size-4"
            /></Button>
            <Button
              variant="outline"
              size="icon"
              as="a"
              :href="address"
              target="_blank"
              :aria-label="$t('portal.settings.openPortal')"
              ><ExternalLink class="size-4"
            /></Button>
          </div>
          <p class="text-xs text-muted-foreground">{{ $t('portal.settings.addressHint') }}</p>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
