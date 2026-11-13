<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import {
  API_KEY_PERMISSIONS,
  apiKeysApi,
  READ_PERMISSIONS,
  type ApiKey,
  type ApiKeyPermission,
  type CreatedApiKey,
} from '../api'

/** Creates a key (the answer carries the key itself) or changes the name and permissions of one. */
const props = defineProps<{ tenantId: string; apiKey: ApiKey | null }>()
const emit = defineEmits<{ created: [created: CreatedApiKey]; saved: [key: ApiKey] }>()
const open = defineModel<boolean>('open', { default: false })

const PRESETS = {
  read: READ_PERMISSIONS,
  all: API_KEY_PERMISSIONS,
  none: [],
} as const satisfies Record<string, readonly ApiKeyPermission[]>

const { t } = useI18n()
const name = ref('')
const permissions = ref<ApiKeyPermission[]>([])
const error = ref<string | null>(null)
const busy = ref(false)

/** The permissions by area (`calls.view` belongs to `calls`), like on the roles page. */
const groups = computed(() => {
  const areas = new Map<string, ApiKeyPermission[]>()
  for (const permission of API_KEY_PERMISSIONS) {
    const area = permission.split('.')[0]!
    areas.set(area, [...(areas.get(area) ?? []), permission])
  }
  return [...areas]
})

/** As on the roles page. */
function label(permission: ApiKeyPermission): string {
  return t(`roles.permissions.${permission}`)
}

watch(open, (isOpen) => {
  if (!isOpen) {
    return
  }
  error.value = null
  name.value = props.apiKey?.name ?? ''
  permissions.value = [...(props.apiKey?.permissions ?? READ_PERMISSIONS)]
})

function toggle(permission: ApiKeyPermission, on: boolean | 'indeterminate'): void {
  permissions.value =
    on === true ? [...permissions.value, permission] : permissions.value.filter((each) => each !== permission)
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    const body = {
      name: name.value.trim(),
      permissions: API_KEY_PERMISSIONS.filter((permission) => permissions.value.includes(permission)),
    }
    if (props.apiKey) {
      emit('saved', await apiKeysApi.update(props.tenantId, props.apiKey.id, body))
    } else {
      emit('created', await apiKeysApi.create(props.tenantId, body))
    }
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
    <DialogContent class="max-h-[90vh] overflow-y-auto sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ apiKey ? $t('apiKeys.edit') : $t('apiKeys.create') }}</DialogTitle>
        <DialogDescription>{{ $t('apiKeys.dialogText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="api-key-name">{{ $t('common.name') }}</Label>
          <Input
            id="api-key-name"
            v-model="name"
            :placeholder="$t('apiKeys.namePlaceholder')"
            maxlength="80"
            required
          />
        </div>
        <fieldset class="grid gap-3">
          <legend class="mb-2 text-sm font-medium">{{ $t('apiKeys.permissions') }}</legend>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="(chosen, preset) in PRESETS"
              :key="preset"
              type="button"
              variant="outline"
              size="sm"
              :data-test="`preset-${preset}`"
              @click="permissions = [...chosen]"
            >
              {{ $t(`apiKeys.presets.${preset}`) }}
            </Button>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div v-for="[area, members] in groups" :key="area" class="grid content-start gap-2">
              <p class="text-xs font-medium text-muted-foreground">{{ $t(`roles.groups.${area}`) }}</p>
              <label v-for="permission in members" :key="permission" class="flex items-start gap-2 text-sm">
                <Checkbox
                  class="mt-0.5"
                  :model-value="permissions.includes(permission)"
                  :data-test="`permission-${permission}`"
                  @update:model-value="(on) => toggle(permission, on)"
                />
                <span>{{ label(permission) }}</span>
              </label>
            </div>
          </div>
        </fieldset>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !permissions.length" data-test="save-key">
            {{ apiKey ? $t('common.save') : $t('apiKeys.create') }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
