<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import type { Queue } from '@/modules/access/api'
import { SECURITIES, type AccountRequest, type EmailAccount, type Security } from '../api'

/**
 * Sets up a mailbox: address, IMAP to fetch, SMTP to send (or incoming mail only), and its default queue. Passwords are
 * only sent when typed.
 */
const props = defineProps<{
  title: string
  initial: EmailAccount | null
  queues: Queue[]
  save: (body: AccountRequest) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

interface ServerForm {
  host: string
  port: string
  security: Security
  username: string
  password: string
}

const form = ref({
  name: '',
  address: '',
  display_name: '',
  queue_id: '',
  folder: 'INBOX',
  active: true,
})
const imap = ref<ServerForm>({ host: '', port: '993', security: 'ssl', username: '', password: '' })
const smtp = ref<ServerForm>({ host: '', port: '587', security: 'starttls', username: '', password: '' })
/** Replies can go out by it (SMTP); off: a mailbox for incoming mail only. */
const sends = ref(true)
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (!opened) {
    return
  }
  const account = props.initial
  form.value = {
    name: account?.name ?? '',
    address: account?.address ?? '',
    display_name: account?.display_name ?? '',
    queue_id: account?.queue_id ?? props.queues[0]?.id ?? '',
    folder: account?.folder ?? 'INBOX',
    active: account?.active ?? true,
  }
  imap.value = account
    ? { ...account.imap, port: String(account.imap.port), password: '' }
    : { host: '', port: '993', security: 'ssl', username: '', password: '' }
  smtp.value = account?.smtp
    ? { ...account.smtp, port: String(account.smtp.port), password: '' }
    : { host: '', port: '587', security: 'starttls', username: account?.address ?? '', password: '' }
  sends.value = account ? account.smtp !== null : true
  error.value = null
})

/** Typing the address fills in the user names and guesses the servers (imap./smtp. of its domain). */
watch(
  () => form.value.address,
  (address, before) => {
    const domain = address.split('@')[1]
    for (const [server, prefix] of [
      [imap, 'imap'],
      [smtp, 'smtp'],
    ] as const) {
      if (!server.value.username || server.value.username === before) {
        server.value.username = address
      }
      if (domain && (!server.value.host || server.value.host === `${prefix}.${before?.split('@')[1]}`)) {
        server.value.host = `${prefix}.${domain}`
      }
    }
  },
)

const securityOptions = computed(() =>
  SECURITIES.map((value) => ({ value, label: value === 'none' ? 'none' : value.toUpperCase() })),
)

function server(values: ServerForm) {
  return {
    host: values.host,
    port: Number(values.port),
    security: values.security,
    username: values.username,
    password: values.password || null,
  }
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save({ ...form.value, imap: server(imap.value), smtp: sends.value ? server(smtp.value) : null })
    open.value = false
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ $t('channels.accounts.dialogText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <p v-if="initial?.provider" class="text-sm text-muted-foreground" data-test="oauth-note">
          {{
            $t('channels.accounts.connect.fixed', {
              provider: $t(`channels.accounts.connect.name.${initial.provider}`),
              address: initial.address,
            })
          }}
        </p>
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-if="!initial?.provider" class="grid gap-2">
            <Label for="account-address">{{ $t('channels.accounts.address') }}</Label>
            <Input id="account-address" v-model="form.address" type="email" required autofocus />
          </div>
          <div class="grid gap-2">
            <Label for="account-name">{{ $t('channels.name') }}</Label>
            <Input id="account-name" v-model="form.name" maxlength="80" required />
          </div>
          <div class="grid gap-2">
            <Label for="account-display">{{ $t('channels.accounts.displayName') }}</Label>
            <Input
              id="account-display"
              v-model="form.display_name"
              maxlength="80"
              :placeholder="$t('channels.accounts.displayNamePlaceholder')"
            />
          </div>
        </div>
        <label v-if="!initial?.provider" class="flex items-center gap-3 text-sm">
          <Switch v-model="sends" data-test="account-sends" />
          {{ $t('channels.accounts.sends') }}
        </label>
        <fieldset
          v-for="[kind, values] in initial?.provider
            ? []
            : sends
              ? ([
                  ['imap', imap],
                  ['smtp', smtp],
                ] as const)
              : ([['imap', imap]] as const)"
          :key="kind"
          class="grid gap-3 rounded-md border p-3"
        >
          <legend class="px-1 text-sm font-medium">{{ $t(`channels.accounts.${kind}`) }}</legend>
          <div class="grid gap-3 sm:grid-cols-[1fr_6rem_8rem]">
            <div class="grid gap-1">
              <Label :for="`${kind}-host`" class="text-xs">{{ $t('channels.accounts.host') }}</Label>
              <Input :id="`${kind}-host`" v-model="values.host" required />
            </div>
            <div class="grid gap-1">
              <Label :for="`${kind}-port`" class="text-xs">{{ $t('channels.accounts.port') }}</Label>
              <Input :id="`${kind}-port`" v-model="values.port" type="number" min="1" max="65535" required />
            </div>
            <div class="grid gap-1">
              <Label :for="`${kind}-security`" class="text-xs">{{ $t('channels.accounts.security') }}</Label>
              <NativeSelect :id="`${kind}-security`" v-model="values.security" :options="securityOptions" />
            </div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="grid gap-1">
              <Label :for="`${kind}-username`" class="text-xs">{{ $t('channels.accounts.username') }}</Label>
              <Input :id="`${kind}-username`" v-model="values.username" autocomplete="off" />
            </div>
            <div class="grid gap-1">
              <Label :for="`${kind}-password`" class="text-xs">{{ $t('channels.accounts.password') }}</Label>
              <Input
                :id="`${kind}-password`"
                v-model="values.password"
                type="password"
                autocomplete="new-password"
                :placeholder="initial?.[kind]?.has_password ? $t('channels.accounts.keepPassword') : ''"
              />
            </div>
          </div>
        </fieldset>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="grid gap-2">
            <Label for="account-folder">{{ $t('channels.accounts.folder') }}</Label>
            <Input id="account-folder" v-model="form.folder" maxlength="200" />
          </div>
          <label class="flex items-center gap-3 self-end text-sm">
            <Switch v-model="form.active" data-test="account-active" />
            {{ $t('channels.accounts.active') }}
          </label>
        </div>
        <div class="grid gap-2 rounded-md border p-3">
          <Label for="account-queue">{{ $t('channels.accounts.queue') }}</Label>
          <NativeSelect
            id="account-queue"
            v-model="form.queue_id"
            :options="queues.map((queue) => ({ value: queue.id, label: queue.name }))"
          />
          <p class="text-xs text-muted-foreground">{{ $t('channels.accounts.queueHint') }}</p>
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !form.address.trim() || !form.queue_id" data-test="save-account">
            {{ $t('common.save') }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
