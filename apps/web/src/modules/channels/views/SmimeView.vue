<script setup lang="ts">
import { FileKey, Plus, ShieldCheck, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import SegmentedControl from '@/core/components/SegmentedControl.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDate } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { useTenants } from '@/modules/tenancy/tenants'
import { CERTIFICATE_KINDS, channelsApi, type CertificateKind, type SmimeCertificate } from '../api'

/**
 * S/MIME: our certificates with their keys (to sign and to decrypt), the customers' certificates (to encrypt to
 * them; trusted senders' come by themselves) and the authorities whose certificates count as trusted.
 */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const certificates = useAsyncData(() => channelsApi.certificates(tenantId.value))

const kind = ref<CertificateKind>('own')
const kinds = computed(() => CERTIFICATE_KINDS.map((value) => ({ value, label: t(`channels.smime.kinds.${value}`) })))
const shown = computed(() => (certificates.data.value ?? []).filter((each) => each.kind === kind.value))

const SOON_DAYS = 30

function validity(certificate: SmimeCertificate): 'expired' | 'soon' | 'valid' {
  const left = new Date(certificate.not_after).getTime() - Date.now()
  if (left < 0) return 'expired'
  return left < SOON_DAYS * 24 * 60 * 60 * 1000 ? 'soon' : 'valid'
}

const addOpen = ref(false)
const file = ref<File | null>(null)
const keyFile = ref<File | null>(null)
const password = ref('')
const addError = ref<string | null>(null)
const busy = ref(false)

function openAdd(): void {
  file.value = null
  keyFile.value = null
  password.value = ''
  addError.value = null
  addOpen.value = true
}

function picked(event: Event): File | null {
  return (event.target as HTMLInputElement).files?.[0] ?? null
}

async function add(): Promise<void> {
  if (!file.value) return
  busy.value = true
  try {
    const added = await channelsApi.addCertificate(
      tenantId.value,
      kind.value,
      file.value,
      password.value,
      keyFile.value,
    )
    notify.success(t('channels.smime.added', { name: added.emails[0] ?? added.subject }))
    addOpen.value = false
    await certificates.reload()
  } catch (caught) {
    addError.value = errorText(caught)
  } finally {
    busy.value = false
  }
}

const deleting = ref<SmimeCertificate | null>(null)
const deleteOpen = ref(false)

function askDelete(certificate: SmimeCertificate): void {
  deleting.value = certificate
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  await channelsApi.deleteCertificate(tenantId.value, deleting.value!.id)
  notify.success(t('channels.smime.deleted'))
  await certificates.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-6xl gap-6">
    <PageHeader :title="$t('channels.smime.title')" :description="$t('channels.smime.description')">
      <Button data-test="add-certificate" @click="openAdd"
        ><Plus class="size-4" /> {{ $t('channels.smime.add') }}</Button
      >
    </PageHeader>
    <SegmentedControl v-model="kind" :options="kinds" :label="$t('channels.smime.title')" />
    <p class="text-sm text-muted-foreground">{{ $t(`channels.smime.hints.${kind}`) }}</p>
    <ErrorAlert v-if="certificates.error.value" :message="certificates.error.value" />
    <EmptyState
      v-else-if="certificates.data.value && shown.length === 0"
      :title="$t('channels.smime.empty')"
      description=""
    >
      <template #icon><ShieldCheck class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="certificates.data.value">
      <CardContent class="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{{ $t('channels.smime.addresses') }}</TableHead>
              <TableHead>{{ $t('channels.smime.issuer') }}</TableHead>
              <TableHead>{{ $t('channels.smime.validUntil') }}</TableHead>
              <TableHead>{{ $t('channels.smime.fingerprint') }}</TableHead>
              <TableHead class="text-right">{{ $t('common.actions') }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="certificate in shown" :key="certificate.id" data-test="certificate">
              <TableCell class="max-w-64">
                <span class="block truncate font-medium">{{
                  certificate.emails.join(', ') || certificate.subject
                }}</span>
                <span class="block truncate text-xs text-muted-foreground">{{ certificate.subject }}</span>
              </TableCell>
              <TableCell class="max-w-56 truncate text-xs">{{ certificate.issuer }}</TableCell>
              <TableCell class="whitespace-nowrap">
                {{ formatDate(certificate.not_after) }}
                <Badge
                  v-if="validity(certificate) !== 'valid'"
                  :variant="validity(certificate) === 'expired' ? 'destructive' : 'secondary'"
                  class="ml-2"
                  :data-test="`validity-${certificate.id}`"
                  >{{ $t(`channels.smime.${validity(certificate)}`) }}</Badge
                >
                <Badge v-if="certificate.has_key" variant="outline" class="ml-2"
                  ><FileKey class="size-3" /> {{ $t('channels.smime.withKey') }}</Badge
                >
              </TableCell>
              <TableCell class="font-mono text-xs" :title="certificate.fingerprint">
                {{ certificate.fingerprint.slice(0, 16) }}…
              </TableCell>
              <TableCell class="text-right">
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.delete')"
                  :data-test="`delete-${certificate.id}`"
                  @click="askDelete(certificate)"
                  ><Trash2 class="size-4"
                /></Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>

    <Dialog v-model:open="addOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{{ $t('channels.smime.addTitle', { kind: $t(`channels.smime.kinds.${kind}`) }) }}</DialogTitle>
          <DialogDescription>{{ $t(`channels.smime.files.${kind}`) }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="add">
          <ErrorAlert v-if="addError" :message="addError" />
          <div class="grid gap-2">
            <Label for="smime-file">{{ $t(kind === 'own' ? 'channels.smime.ownFile' : 'channels.smime.file') }}</Label>
            <Input
              id="smime-file"
              type="file"
              accept=".p12,.pfx,.pem,.crt,.cer,.der"
              data-test="certificate-file"
              @change="(event: Event) => (file = picked(event))"
            />
          </div>
          <template v-if="kind === 'own'">
            <div class="grid gap-2">
              <Label for="smime-password">{{ $t('channels.smime.password') }}</Label>
              <Input
                id="smime-password"
                v-model="password"
                type="password"
                autocomplete="off"
                maxlength="1000"
                data-test="certificate-password"
              />
            </div>
            <div class="grid gap-2">
              <Label for="smime-key">{{ $t('channels.smime.keyFile') }}</Label>
              <Input
                id="smime-key"
                type="file"
                accept=".pem,.key,.der"
                data-test="certificate-key"
                @change="(event: Event) => (keyFile = picked(event))"
              />
              <p class="text-xs text-muted-foreground">{{ $t('channels.smime.keyHint') }}</p>
            </div>
          </template>
          <DialogFooter>
            <Button type="submit" :disabled="!file || busy" data-test="save-certificate">{{
              $t('common.save')
            }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('channels.smime.deleteTitle', { name: deleting?.emails[0] ?? deleting?.subject })"
      :description="$t(deleting?.kind === 'own' ? 'channels.smime.deleteOwnText' : 'channels.smime.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
