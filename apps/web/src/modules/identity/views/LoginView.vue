<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiRequestError } from '@/core/api/http'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NoticeAlert from '@/core/components/NoticeAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { useInstance } from '@/core/instance'
import { notify } from '@/core/notify'
import { safeRedirect } from '@/core/router/guard'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi } from '../api'
import AuthCard from '../components/AuthCard.vue'
import TwoFactorStep from '../components/TwoFactorStep.vue'
import { useSession } from '../session'

const session = useSession()
// A self-hosted instance: accounts come from invitations, so there is no sign-up link.
const { selfHosted } = useInstance()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const notVerified = ref(false)
const resent = ref(false)
const busy = ref(false)
/** Set after the password when the account has two-factor login. */
const challenge = ref<string | null>(null)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  notVerified.value = false
  resent.value = false
  try {
    challenge.value = await session.login(email.value, password.value)
    if (!challenge.value) {
      await done()
    }
  } catch (caught) {
    notVerified.value = caught instanceof ApiRequestError && caught.code === 'email_not_verified'
    error.value = notVerified.value ? null : errorText(caught)
  } finally {
    busy.value = false
  }
}

async function done(): Promise<void> {
  await router.replace(safeRedirect(route.query.redirect))
}

function back(): void {
  challenge.value = null
  password.value = ''
}

async function resend(): Promise<void> {
  try {
    await identityApi.resendConfirmation({ email: email.value, password: password.value })
    resent.value = true
  } catch (caught) {
    notify.error(caught)
  }
}
</script>

<template>
  <AuthCard v-if="challenge" :title="$t('login.codeTitle')" :description="email">
    <TwoFactorStep :challenge="challenge" @done="done" @back="back" />
  </AuthCard>
  <AuthCard v-else :title="$t('login.title')" :description="$t('login.description')">
    <form class="grid gap-4" @submit.prevent="submit">
      <ErrorAlert v-if="error" :title="$t('login.failed')" :message="error" />
      <NoticeAlert v-if="notVerified" :title="$t('errors.email_not_verified')" :message="$t('login.notVerified')">
        <Button v-if="!resent" variant="link" class="h-auto p-0" type="button" data-test="resend" @click="resend">
          {{ $t('login.resend') }}
        </Button>
        <span v-else data-test="resent">{{ $t('login.resent') }}</span>
      </NoticeAlert>
      <div class="grid gap-2">
        <Label for="email">{{ $t('common.email') }}</Label>
        <Input id="email" v-model="email" type="email" autocomplete="email" required autofocus />
      </div>
      <div class="grid gap-2">
        <div class="flex items-center justify-between">
          <Label for="password">{{ $t('common.password') }}</Label>
          <RouterLink :to="{ name: 'forgot-password' }" class="text-sm text-primary hover:underline">
            {{ $t('login.forgot') }}
          </RouterLink>
        </div>
        <Input id="password" v-model="password" type="password" autocomplete="current-password" required />
      </div>
      <Button type="submit" :disabled="busy || !email || !password" data-test="submit">
        {{ busy ? $t('login.busy') : $t('login.submit') }}
      </Button>
      <p v-if="!selfHosted" class="text-center text-sm text-muted-foreground" data-test="sign-up">
        {{ $t('login.noAccount') }}
        <RouterLink :to="{ name: 'register' }" class="text-primary hover:underline">{{
          $t('login.register')
        }}</RouterLink>
      </p>
    </form>
  </AuthCard>
</template>
