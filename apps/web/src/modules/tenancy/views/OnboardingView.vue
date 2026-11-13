<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText, LOCALES, type Locale } from '@/core/i18n/i18n'
import { useInstance } from '@/core/instance'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { tenancyApi } from '../api'
import { useTenants } from '../tenants'
import { browserTimezone, timezones } from '@/core/timezones'

const { t, locale } = useI18n()
const router = useRouter()
const tenants = useTenants()
// A self-hosted instance has its one organization; whoever is in none waits for an invitation.
const { selfHosted } = useInstance()

const name = ref('')
const timezone = ref(browserTimezone())
const language = ref<Locale>(locale.value as Locale)
const error = ref<string | null>(null)
const busy = ref(false)

const zoneOptions = computed(() => timezones().map((zone) => ({ value: zone, label: zone.replaceAll('_', ' ') })))
const languageOptions = computed(() => LOCALES.map((value) => ({ value, label: t(`locale.${value}`) })))

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    const tenant = await tenancyApi.create({ name: name.value, timezone: timezone.value, locale: language.value })
    tenants.put(tenant)
    notify.success(t('onboarding.created', { name: tenant.name }))
    await router.push({ name: 'overview', params: { tenantId: tenant.id } })
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex justify-center px-4 py-12 sm:py-20">
    <Card class="w-full max-w-lg">
      <CardHeader>
        <CardTitle class="text-xl">{{ $t(selfHosted ? 'onboarding.noOrganization' : 'onboarding.title') }}</CardTitle>
        <CardDescription v-if="!selfHosted">{{ $t('onboarding.description') }}</CardDescription>
      </CardHeader>
      <CardContent v-if="selfHosted">
        <p class="text-sm text-muted-foreground" data-test="wait-for-invitation">{{ $t('onboarding.selfHosted') }}</p>
      </CardContent>
      <CardContent v-else>
        <form class="grid gap-4" @submit.prevent="submit">
          <ErrorAlert v-if="error" :title="$t('common.error')" :message="error" />
          <div class="grid gap-2">
            <Label for="name">{{ $t('onboarding.name') }}</Label>
            <Input id="name" v-model="name" :placeholder="$t('onboarding.namePlaceholder')" required autofocus />
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
          <Button type="submit" :disabled="busy || !name.trim()" data-test="submit">
            {{ busy ? $t('onboarding.busy') : $t('onboarding.submit') }}
          </Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
