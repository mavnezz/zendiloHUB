<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi } from '../api'
import { useSession } from '../session'

const { t } = useI18n()
const router = useRouter()
const session = useSession()
const open = ref(false)
const password = ref('')

function ask(): void {
  password.value = ''
  open.value = true
}

async function deleteAccount(): Promise<void> {
  await identityApi.deleteAccount(password.value)
  session.expire()
  notify.success(t('account.deleted'))
  await router.replace({ name: 'start' })
}
</script>

<template>
  <Card class="border-destructive/40">
    <CardHeader>
      <CardTitle>{{ $t('account.danger') }}</CardTitle>
      <CardDescription>{{ $t('account.dangerText') }}</CardDescription>
    </CardHeader>
    <CardContent>
      <Button variant="destructive" data-test="delete-account" @click="ask">{{ $t('account.deleteButton') }}</Button>
    </CardContent>
    <ConfirmDialog
      v-model:open="open"
      :title="$t('account.deleteTitle')"
      :description="$t('account.deleteText')"
      :confirm-label="$t('account.deleteConfirm')"
      :action="deleteAccount"
    >
      <div class="grid gap-2">
        <Label for="delete-password">{{ $t('common.password') }}</Label>
        <Input
          id="delete-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          data-test="delete-password"
        />
      </div>
    </ConfirmDialog>
  </Card>
</template>
