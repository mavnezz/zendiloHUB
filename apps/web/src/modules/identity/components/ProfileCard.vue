<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SegmentedControl from '@/core/components/SegmentedControl.vue'
import { LOCALES, setLocale, type Locale } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi } from '../api'
import { useSession } from '../session'

const { t } = useI18n()
const session = useSession()

const localeOptions = computed(() => LOCALES.map((value) => ({ value, label: t(`locale.${value}`) })))
const accountLocale = computed({
  get: () => session.user.value?.locale ?? 'en',
  set: (value: Locale) => void changeLocale(value),
})

async function changeLocale(value: Locale): Promise<void> {
  try {
    session.replaceUser(await identityApi.updateAccount({ locale: value }))
    setLocale(value)
    notify.success(t('common.saved'))
  } catch (caught) {
    notify.error(caught)
  }
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ $t('account.profile') }}</CardTitle>
      <CardDescription>{{ $t('account.profileText') }}</CardDescription>
    </CardHeader>
    <CardContent class="grid gap-4 sm:grid-cols-2">
      <div class="grid gap-2">
        <Label for="account-email">{{ $t('common.email') }}</Label>
        <Input id="account-email" :model-value="session.user.value?.email" disabled />
      </div>
      <div class="grid gap-2">
        <span class="text-sm font-medium">{{ $t('account.language') }}</span>
        <SegmentedControl v-model="accountLocale" :options="localeOptions" :label="$t('account.language')" />
      </div>
    </CardContent>
  </Card>
</template>
