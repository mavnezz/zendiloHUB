<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText, LOCALES, type Locale } from '@/core/i18n/i18n'
import { useInstance } from '@/core/instance'
import { notify } from '@/core/notify'
import { browserTimezone, timezones } from '@/core/timezones'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi, PASSWORD_MIN_LENGTH } from '../api'
import AuthCard from '../components/AuthCard.vue'
import { useSession } from '../session'

/**
 * The setup wizard of a self-hosted instance: the code from the server log, the first administrator and the
 * organization, in one step. Afterwards it is gone for good.
 */
const { t, locale } = useI18n()
const router = useRouter()
const session = useSession()
const instance = useInstance()

const token = ref('')
const email = ref('')
const password = ref('')
const organization = ref('')
const timezone = ref(browserTimezone())
const language = ref<Locale>(locale.value as Locale)
const error = ref<string | null>(null)
const busy = ref(false)

const zoneOptions = computed(() => timezones().map((zone) => ({ value: zone, label: zone.replaceAll('_', ' ') })))
const languageOptions = computed(() => LOCALES.map((value) => ({ value, label: t(`locale.${value}`) })))
const complete = computed(
  () => token.value.trim() && email.value.trim() && password.value.length > 0 && organization.value.trim(),
)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    const result = await identityApi.completeSetup({
      token: token.value.trim(),
      email: email.value,
      password: password.value,
      organization_name: organization.value,
      timezone: timezone.value,
      locale: language.value,
    })
    instance.setUp()
    session.start(result.user)
    notify.success(t('setup.done', { name: organization.value.trim() }))
    await router.replace({ name: 'start' })
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="$t('setup.title')" :description="$t('setup.description')">
    <form class="grid gap-4" @submit.prevent="submit">
      <ErrorAlert v-if="error" :title="$t('setup.failed')" :message="error" />
      <div class="grid gap-2">
        <Label for="token">{{ $t('setup.token') }}</Label>
        <Input id="token" v-model="token" autocomplete="off" spellcheck="false" required autofocus />
        <p class="text-xs text-muted-foreground">{{ $t('setup.tokenHint') }}</p>
      </div>
      <div class="grid gap-2">
        <Label for="organization">{{ $t('setup.organization') }}</Label>
        <Input id="organization" v-model="organization" :placeholder="$t('onboarding.namePlaceholder')" required />
      </div>
      <div class="grid gap-2">
        <Label for="email">{{ $t('setup.email') }}</Label>
        <Input id="email" v-model="email" type="email" autocomplete="email" required />
      </div>
      <div class="grid gap-2">
        <Label for="password">{{ $t('common.password') }}</Label>
        <Input id="password" v-model="password" type="password" autocomplete="new-password" required />
        <p class="text-xs text-muted-foreground">{{ $t('register.passwordHint', { min: PASSWORD_MIN_LENGTH }) }}</p>
      </div>
      <div class="grid gap-2">
        <Label for="timezone">{{ $t('onboarding.timezone') }}</Label>
        <NativeSelect id="timezone" v-model="timezone" :options="zoneOptions" />
      </div>
      <div class="grid gap-2">
        <Label for="language">{{ $t('onboarding.language') }}</Label>
        <NativeSelect id="language" v-model="language" :options="languageOptions" />
      </div>
      <Button type="submit" :disabled="busy || !complete" data-test="submit">
        {{ busy ? $t('setup.busy') : $t('setup.submit') }}
      </Button>
    </form>
  </AuthCard>
</template>
