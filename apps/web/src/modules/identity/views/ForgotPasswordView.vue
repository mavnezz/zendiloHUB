<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NoticeAlert from '@/core/components/NoticeAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi } from '../api'
import AuthCard from '../components/AuthCard.vue'

const { t } = useI18n()
const email = ref('')
const error = ref<string | null>(null)
const sentTo = ref<string | null>(null)
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await identityApi.forgotPassword(email.value)
    sentTo.value = email.value.trim()
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthCard :title="$t('forgot.title')" :description="$t('forgot.description')">
    <NoticeAlert v-if="sentTo" :title="$t('forgot.sentTitle')" :message="t('forgot.sentText', { email: sentTo })" />
    <form v-else class="grid gap-4" @submit.prevent="submit">
      <ErrorAlert v-if="error" :message="error" />
      <div class="grid gap-2">
        <Label for="email">{{ $t('common.email') }}</Label>
        <Input id="email" v-model="email" type="email" autocomplete="email" required autofocus />
      </div>
      <Button type="submit" :disabled="busy || !email" data-test="submit">
        {{ busy ? $t('forgot.busy') : $t('forgot.submit') }}
      </Button>
    </form>
    <RouterLink :to="{ name: 'login' }" class="text-center text-sm text-primary hover:underline">
      {{ $t('forgot.back') }}
    </RouterLink>
  </AuthCard>
</template>
