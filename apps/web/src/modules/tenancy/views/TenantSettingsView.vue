<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { errorText, LOCALES, type Locale } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { tenancyApi } from '../api'
import { useTenants } from '../tenants'
import { timezones } from '@/core/timezones'

const { t } = useI18n()
const router = useRouter()
const tenants = useTenants()
/** Null for a moment after leaving or deleting the organization, until the router leaves this page. */
const current = computed(() => tenants.current.value)
const tenant = computed(() => current.value!)

const name = ref(tenant.value.name)
const timezone = ref(tenant.value.timezone)
const language = ref<Locale>(tenant.value.locale)
const error = ref<string | null>(null)
const busy = ref(false)

const zoneOptions = computed(() => timezones().map((zone) => ({ value: zone, label: zone.replaceAll('_', ' ') })))
const languageOptions = computed(() => LOCALES.map((value) => ({ value, label: t(`locale.${value}`) })))

async function save(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    tenants.put(
      await tenancyApi.update(tenant.value.id, { name: name.value, timezone: timezone.value, locale: language.value }),
    )
    notify.success(t('tenantSettings.saved'))
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}

const deleteOpen = ref(false)
const confirmation = ref('')

function askDelete(): void {
  confirmation.value = ''
  deleteOpen.value = true
}

async function destroy(): Promise<void> {
  const { id, name: deletedName } = tenant.value
  await tenancyApi.delete(id)
  notify.success(t('tenantSettings.deleted', { name: deletedName }))
  tenants.forget(id)
  await router.push({ name: 'start' })
}
</script>

<template>
  <div v-if="current" class="mx-auto grid max-w-3xl gap-6">
    <PageHeader
      :title="$t('tenantSettings.title')"
      :description="$t('tenantSettings.description', { name: tenant.name })"
    />

    <Card>
      <CardHeader>
        <CardTitle>{{ $t('tenantSettings.general') }}</CardTitle>
      </CardHeader>
      <CardContent>
        <form class="grid gap-4" @submit.prevent="save">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-2">
            <Label for="name">{{ $t('onboarding.name') }}</Label>
            <Input id="name" v-model="name" required />
          </div>
          <div class="grid gap-2">
            <Label for="timezone">{{ $t('onboarding.timezone') }}</Label>
            <NativeSelect id="timezone" v-model="timezone" :options="zoneOptions" />
            <p class="text-xs text-muted-foreground">{{ $t('onboarding.timezoneHint') }}</p>
          </div>
          <div class="grid gap-2">
            <Label for="language">{{ $t('onboarding.language') }}</Label>
            <NativeSelect id="language" v-model="language" :options="languageOptions" />
          </div>
          <div>
            <Button type="submit" :disabled="busy || !name.trim()" data-test="save">{{ $t('common.save') }}</Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <Card v-if="tenants.can('tenant.delete')" class="border-destructive/40">
      <CardHeader>
        <CardTitle>{{ $t('tenantSettings.danger') }}</CardTitle>
        <CardDescription>{{ $t('tenantSettings.dangerText') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="destructive" data-test="delete" @click="askDelete">
          {{ $t('tenantSettings.deleteButton') }}
        </Button>
      </CardContent>
    </Card>

    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('tenantSettings.deleteTitle', { name: tenant.name })"
      :description="$t('tenantSettings.deleteText')"
      :confirm-label="$t('tenantSettings.deleteConfirm')"
      :blocked="confirmation.trim() !== tenant.name"
      :action="destroy"
    >
      <Input v-model="confirmation" :aria-label="$t('onboarding.name')" data-test="delete-confirmation" />
    </ConfirmDialog>
  </div>
</template>
