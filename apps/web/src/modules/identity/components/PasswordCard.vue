<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi, PASSWORD_MIN_LENGTH } from '../api'

const { t } = useI18n()
const currentPassword = ref('')
const newPassword = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

async function changePassword(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await identityApi.changePassword({ current_password: currentPassword.value, new_password: newPassword.value })
    currentPassword.value = ''
    newPassword.value = ''
    notify.success(t('account.passwordChanged'))
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ $t('account.password') }}</CardTitle>
      <CardDescription>{{ $t('account.passwordText') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <form class="grid gap-4 sm:grid-cols-2" data-test="password-form" @submit.prevent="changePassword">
        <ErrorAlert v-if="error" class="sm:col-span-2" :message="error" />
        <div class="grid gap-2">
          <Label for="current-password">{{ $t('account.currentPassword') }}</Label>
          <Input
            id="current-password"
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            required
          />
        </div>
        <div class="grid gap-2">
          <Label for="new-password">{{ $t('account.newPassword') }}</Label>
          <Input
            id="new-password"
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            :minlength="PASSWORD_MIN_LENGTH"
            required
          />
        </div>
        <div class="sm:col-span-2">
          <Button
            type="submit"
            :disabled="busy || !currentPassword || newPassword.length < PASSWORD_MIN_LENGTH"
            data-test="change-password"
          >
            {{ $t('account.password') }}
          </Button>
        </div>
      </form>
    </CardContent>
  </Card>
</template>
