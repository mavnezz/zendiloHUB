<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi } from '../api'

/** What the caller adds to the queues' signatures: their name, title and own lines. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const form = ref({ name: '', title: '', signature: '' })
const error = ref<string | null>(null)
const busy = ref(false)

onMounted(async () => {
  try {
    form.value = await channelsApi.personal(tenantId.value)
  } catch (caught) {
    error.value = errorText(caught)
  }
})

async function save(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    form.value = await channelsApi.setPersonal(tenantId.value, form.value)
    notify.success(t('channels.personal.saved'))
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto grid max-w-2xl gap-6">
    <PageHeader :title="$t('channels.personal.title')" :description="$t('channels.personal.description')" />
    <Card>
      <CardContent class="pt-6">
        <form class="grid gap-4" @submit.prevent="save">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="grid gap-2">
              <Label for="personal-name">{{ $t('channels.personal.name') }}</Label>
              <Input id="personal-name" v-model="form.name" maxlength="80" />
            </div>
            <div class="grid gap-2">
              <Label for="personal-title">{{ $t('channels.personal.jobTitle') }}</Label>
              <Input id="personal-title" v-model="form.title" maxlength="80" />
            </div>
          </div>
          <div class="grid gap-2">
            <Label for="personal-signature">{{ $t('channels.personal.lines') }}</Label>
            <Textarea id="personal-signature" v-model="form.signature" rows="4" />
            <p class="text-xs text-muted-foreground">{{ $t('channels.personal.hint') }}</p>
          </div>
          <div class="flex justify-end">
            <Button type="submit" :disabled="busy" data-test="save-personal">{{ $t('common.save') }}</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
