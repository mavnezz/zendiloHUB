<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi, PASSWORD_MIN_LENGTH } from '../api'
import AuthCard from '../components/AuthCard.vue'
import TwoFactorStep from '../components/TwoFactorStep.vue'
import { useSession } from '../session'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSession()
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const password = ref('')
const error = ref<string | null>(token.value ? null : t('verify.missing'))
const busy = ref(false)
/** The password is set; with two-factor login the code is still missing. */
const challenge = ref<string | null>(null)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    const result = await identityApi.resetPassword({ token: token.value, password: password.value })
    if (result.challenge) {
      challenge.value = result.challenge
      return
    }
    session.start(result.user)
    await done()
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
async function done(): Promise<void> {
  notify.success(t('reset.done'))
  await router.replace({ name: 'account' })
}
</script>

<template>
  <AuthCard v-if="challenge" :title="$t('login.codeTitle')">
    <TwoFactorStep :challenge="challenge" @done="done" @back="router.replace({ name: 'login' })" />
  </AuthCard>
  <AuthCard v-else :title="$t('reset.title')" :description="$t('reset.description')">
    <form class="grid gap-4" @submit.prevent="submit">
      <ErrorAlert v-if="error" :message="error" />
      <div class="grid gap-2">
        <Label for="password">{{ $t('account.newPassword') }}</Label>
        <Input
          id="password"
          v-model="password"
          type="password"
          autocomplete="new-password"
          :minlength="PASSWORD_MIN_LENGTH"
          required
          autofocus
        />
        <p class="text-xs text-muted-foreground">{{ $t('register.passwordHint', { min: PASSWORD_MIN_LENGTH }) }}</p>
      </div>
      <Button type="submit" :disabled="busy || !token || password.length < PASSWORD_MIN_LENGTH" data-test="submit">
        {{ busy ? $t('reset.busy') : $t('reset.submit') }}
      </Button>
    </form>
  </AuthCard>
</template>
