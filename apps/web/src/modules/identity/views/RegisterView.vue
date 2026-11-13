<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NoticeAlert from '@/core/components/NoticeAlert.vue'
import { errorText, useLocale } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi, PASSWORD_MIN_LENGTH } from '../api'
import AuthCard from '../components/AuthCard.vue'

const { t } = useI18n()
const { locale } = useLocale()
const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const sentTo = ref<string | null>(null)
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await identityApi.register({ email: email.value, password: password.value, locale: locale.value })
    sentTo.value = email.value.trim()
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="$t('register.title')" :description="$t('register.description')">
    <NoticeAlert v-if="sentTo" :title="$t('register.sentTitle')" :message="t('register.sentText', { email: sentTo })" />
    <form v-else class="grid gap-4" @submit.prevent="submit">
      <ErrorAlert v-if="error" :message="error" />
      <div class="grid gap-2">
        <Label for="email">{{ $t('common.email') }}</Label>
        <Input id="email" v-model="email" type="email" autocomplete="email" required autofocus />
      </div>
      <div class="grid gap-2">
        <Label for="password">{{ $t('common.password') }}</Label>
        <Input
          id="password"
          v-model="password"
          type="password"
          autocomplete="new-password"
          :minlength="PASSWORD_MIN_LENGTH"
          required
        />
        <p class="text-xs text-muted-foreground">{{ $t('register.passwordHint', { min: PASSWORD_MIN_LENGTH }) }}</p>
      </div>
      <Button type="submit" :disabled="busy || !email || password.length < PASSWORD_MIN_LENGTH" data-test="submit">
        {{ busy ? $t('register.busy') : $t('register.submit') }}
      </Button>
      <i18n-t keypath="register.consent" tag="p" class="text-center text-xs text-muted-foreground" scope="global">
        <template #terms>
          <RouterLink :to="{ name: 'terms' }" class="underline">{{ $t('footer.terms') }}</RouterLink>
        </template>
        <template #privacy>
          <RouterLink :to="{ name: 'privacy' }" class="underline">{{ $t('footer.privacy') }}</RouterLink>
        </template>
      </i18n-t>
    </form>
    <p class="text-center text-sm text-muted-foreground">
      {{ $t('register.haveAccount') }}
      <RouterLink :to="{ name: 'login' }" class="text-primary hover:underline">{{ $t('register.login') }}</RouterLink>
    </p>
  </AuthCard>
</template>
