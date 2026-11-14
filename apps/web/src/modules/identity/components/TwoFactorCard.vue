<script setup lang="ts">
import QRCode from 'qrcode'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { identityApi, type TwoFactorSetup } from '../api'
import { useSession } from '../session'

type Ask = 'setup' | 'renew' | 'disable'

const { t } = useI18n()
const session = useSession()
const { data: status, error: loadError, reload } = useAsyncData(() => identityApi.twoFactor())

/** A setup waiting for the first code from the app. */
const setup = ref<TwoFactorSetup | null>(null)
const qr = ref('')
const code = ref('')
const error = ref<string | null>(null)
const busy = ref(false)
/** Shown once after turning on or renewing. */
const codes = ref<string[] | null>(null)

const asking = ref<Ask>('setup')
const askOpen = ref(false)
const password = ref('')

function ask(what: Ask): void {
  asking.value = what
  password.value = ''
  askOpen.value = true
}

async function confirmPassword(): Promise<void> {
  if (asking.value === 'setup') {
    setup.value = await identityApi.setupTwoFactor(password.value)
    qr.value = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
      await QRCode.toString(setup.value.uri, { type: 'svg', margin: 1 }),
    )}`
    code.value = ''
    error.value = null
  } else if (asking.value === 'renew') {
    codes.value = (await identityApi.renewRecoveryCodes(password.value)).recovery_codes
  } else {
    await identityApi.disableTwoFactor(password.value)
    notify.success(t('account.twoFactorDisabled'))
    await refresh()
  }
}

async function enable(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    codes.value = (await identityApi.enableTwoFactor(code.value.replace(/\s/g, ''))).recovery_codes
    setup.value = null
    notify.success(t('account.twoFactorEnabled'))
    await refresh()
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}

async function refresh(): Promise<void> {
  await reload()
  const user = session.user.value
  if (user && status.value) {
    session.replaceUser({ ...user, two_factor: status.value.enabled })
  }
}

async function copy(): Promise<void> {
  await navigator.clipboard?.writeText((codes.value ?? []).join('\n'))
  notify.success(t('account.twoFactorCopied'))
}

function download(): void {
  const url = URL.createObjectURL(new Blob([`${(codes.value ?? []).join('\n')}\n`], { type: 'text/plain' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'zendilohub-recovery-codes.txt'
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        {{ $t('account.twoFactor') }}
        <Badge v-if="status" :variant="status.enabled ? 'default' : 'secondary'" data-test="two-factor-state">
          {{ status.enabled ? $t('account.twoFactorOn') : $t('account.twoFactorOff') }}
        </Badge>
      </CardTitle>
      <CardDescription>{{ $t('account.twoFactorText') }}</CardDescription>
    </CardHeader>
    <CardContent class="grid gap-4">
      <ErrorAlert v-if="loadError" :message="loadError" />

      <div v-if="codes" class="grid gap-3 rounded-lg border p-4" data-test="recovery-codes">
        <p class="font-medium">{{ $t('account.twoFactorCodesTitle') }}</p>
        <p class="text-sm text-muted-foreground">{{ $t('account.twoFactorCodesText') }}</p>
        <ul class="grid grid-cols-2 gap-1 font-mono text-sm">
          <li v-for="item in codes" :key="item">{{ item }}</li>
        </ul>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" data-test="copy-codes" @click="copy">{{
            $t('account.twoFactorCopy')
          }}</Button>
          <Button variant="outline" size="sm" data-test="download-codes" @click="download">{{
            $t('account.twoFactorDownload')
          }}</Button>
          <Button size="sm" data-test="codes-done" @click="codes = null">{{ $t('account.twoFactorDone') }}</Button>
        </div>
      </div>

      <form v-else-if="setup" class="grid gap-4" data-test="two-factor-setup" @submit.prevent="enable">
        <p class="text-sm">{{ $t('account.twoFactorScan') }}</p>
        <img :src="qr" alt="" class="size-48 rounded border bg-white" data-test="qr" />
        <div class="grid gap-1">
          <span class="text-sm text-muted-foreground">{{ $t('account.twoFactorSecret') }}</span>
          <code class="font-mono text-sm break-all select-all" data-test="secret">{{ setup.secret }}</code>
        </div>
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid max-w-xs gap-2">
          <Label for="two-factor-code">{{ $t('account.twoFactorCode') }}</Label>
          <Input
            id="two-factor-code"
            v-model="code"
            autocomplete="one-time-code"
            inputmode="numeric"
            maxlength="7"
            required
            data-test="setup-code"
          />
        </div>
        <div class="flex gap-2">
          <Button type="submit" :disabled="busy || !code.trim()" data-test="enable">{{
            $t('account.twoFactorEnable')
          }}</Button>
          <Button type="button" variant="ghost" data-test="cancel-setup" @click="setup = null">{{
            $t('account.twoFactorCancel')
          }}</Button>
        </div>
      </form>

      <template v-else-if="status">
        <div v-if="status.enabled" class="flex flex-wrap items-center gap-2">
          <span class="mr-auto text-sm text-muted-foreground" data-test="codes-left">{{
            $t('account.twoFactorCodesLeft', { count: status.recovery_codes_left })
          }}</span>
          <Button variant="outline" data-test="renew-codes" @click="ask('renew')">{{
            $t('account.twoFactorRenew')
          }}</Button>
          <Button variant="outline" class="text-destructive" data-test="disable-two-factor" @click="ask('disable')">{{
            $t('account.twoFactorDisable')
          }}</Button>
        </div>
        <div v-else>
          <Button data-test="setup-two-factor" @click="ask('setup')">{{ $t('account.twoFactorSetUp') }}</Button>
        </div>
      </template>
    </CardContent>
    <ConfirmDialog
      v-model:open="askOpen"
      :title="
        asking === 'disable'
          ? $t('account.twoFactorDisable')
          : asking === 'renew'
            ? $t('account.twoFactorRenew')
            : $t('account.twoFactorPasswordTitle')
      "
      :description="
        asking === 'disable'
          ? $t('account.twoFactorDisableText')
          : asking === 'renew'
            ? $t('account.twoFactorRenewText')
            : $t('account.twoFactorPasswordText')
      "
      :confirm-label="$t('account.twoFactorContinue')"
      :destructive="asking === 'disable'"
      :blocked="!password"
      :action="confirmPassword"
    >
      <div class="grid gap-2">
        <Label for="two-factor-password">{{ $t('common.password') }}</Label>
        <Input
          id="two-factor-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          data-test="two-factor-password"
        />
      </div>
    </ConfirmDialog>
  </Card>
</template>
