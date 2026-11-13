<script setup lang="ts">
import { KeyRound, Pencil, Plus, Trash2 } from '@lucide/vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDateTime } from '@/core/format'
import { notify } from '@/core/notify'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/core/ui/card'
import { API_KEY_PERMISSIONS, apiKeysApi, READ_PERMISSIONS, type ApiKey, type CreatedApiKey } from '../api'
import ApiKeyDialog from './ApiKeyDialog.vue'
import SecretDialog from './SecretDialog.vue'

/** Keys other systems call the organization's API with; each has its own permissions, the key is shown once. */
const props = defineProps<{ tenantId: string }>()

const { t } = useI18n()
const keys = useAsyncData(() => apiKeysApi.list(props.tenantId))
const editing = ref<ApiKey | null>(null)
const dialogOpen = ref(false)
const secret = ref<string | null>(null)
const secretOpen = ref(false)
const removing = ref<ApiKey | null>(null)
const removeOpen = ref(false)

/** "All permissions", "Read only" or how many. */
function scope(key: ApiKey): string {
  if (key.permissions.length === API_KEY_PERMISSIONS.length) {
    return t('apiKeys.allPermissions')
  }
  const reads = key.permissions.length === READ_PERMISSIONS.length
  if (reads && READ_PERMISSIONS.every((permission) => key.permissions.includes(permission))) {
    return t('apiKeys.readOnly')
  }
  return t('apiKeys.permissionCount', { count: key.permissions.length }, key.permissions.length)
}

function edit(key: ApiKey | null): void {
  editing.value = key
  dialogOpen.value = true
}

async function created(created: CreatedApiKey): Promise<void> {
  notify.success(t('apiKeys.created', { name: created.api_key.name }))
  secret.value = created.key
  secretOpen.value = true
  await keys.reload()
}

async function saved(key: ApiKey): Promise<void> {
  notify.success(t('apiKeys.saved', { name: key.name }))
  await keys.reload()
}

function askRemove(key: ApiKey): void {
  removing.value = key
  removeOpen.value = true
}

async function remove(): Promise<void> {
  await apiKeysApi.remove(props.tenantId, removing.value!.id)
  notify.success(t('apiKeys.deleted', { name: removing.value!.name }))
  await keys.reload()
}
</script>

<template>
  <Card>
    <CardHeader class="flex flex-row items-start justify-between gap-4">
      <div class="grid gap-1.5">
        <CardTitle class="flex items-center gap-2"><KeyRound class="size-4" /> {{ $t('apiKeys.title') }}</CardTitle>
        <p class="text-sm text-muted-foreground">{{ $t('apiKeys.hint') }}</p>
      </div>
      <Button size="sm" data-test="create-key" @click="edit(null)"
        ><Plus class="size-4" /> {{ $t('apiKeys.create') }}</Button
      >
    </CardHeader>
    <CardContent class="grid gap-4">
      <ErrorAlert v-if="keys.error.value" :message="keys.error.value" />
      <ul v-if="keys.data.value?.length" class="divide-y rounded-lg border">
        <li
          v-for="key in keys.data.value"
          :key="key.id"
          class="flex items-center justify-between gap-3 px-3 py-2"
          data-test="api-key"
        >
          <div class="min-w-0">
            <p class="flex flex-wrap items-center gap-2 text-sm font-medium">
              {{ key.name }}
              <Badge variant="outline" :title="key.permissions.join(', ')" data-test="api-key-scope">{{
                scope(key)
              }}</Badge>
              <code class="text-xs text-muted-foreground">{{ key.start }}…</code>
            </p>
            <p class="text-xs text-muted-foreground" data-test="api-key-used">
              {{
                key.last_used_at
                  ? $t('apiKeys.lastUsed', { time: formatDateTime(key.last_used_at) })
                  : $t('apiKeys.neverUsed')
              }}
            </p>
          </div>
          <div class="flex shrink-0 gap-1">
            <Button
              variant="ghost"
              size="icon"
              :aria-label="$t('apiKeys.edit')"
              :data-test="`edit-key-${key.id}`"
              @click="edit(key)"
            >
              <Pencil class="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              :aria-label="$t('common.delete')"
              :data-test="`remove-key-${key.id}`"
              @click="askRemove(key)"
            >
              <Trash2 class="size-4" />
            </Button>
          </div>
        </li>
      </ul>
    </CardContent>
    <ApiKeyDialog
      v-model:open="dialogOpen"
      :tenant-id="tenantId"
      :api-key="editing"
      @created="created"
      @saved="saved"
    />
    <SecretDialog
      v-model:open="secretOpen"
      :secret="secret"
      :title="$t('apiKeys.secretTitle')"
      :text="$t('apiKeys.secretText')"
    />
    <ConfirmDialog
      v-model:open="removeOpen"
      :title="$t('apiKeys.deleteTitle', { name: removing?.name ?? '' })"
      :description="$t('apiKeys.deleteText')"
      :confirm-label="$t('common.delete')"
      :action="remove"
    />
  </Card>
</template>
