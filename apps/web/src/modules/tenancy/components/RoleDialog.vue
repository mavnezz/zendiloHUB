<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import type { Permission, Role, RoleRequest } from '../api'

/** Creates or changes an own role: name, description and its permissions (only what the caller may do). */
const props = defineProps<{
  title: string
  initial: Role | null
  permissions: Permission[]
  /** What the caller may give: their own permissions minus what only owners may hold. */
  grantable: Permission[]
  save: (body: RoleRequest) => Promise<unknown>
}>()
const open = defineModel<boolean>('open', { default: false })

const name = ref('')
const text = ref('')
const chosen = ref(new Set<Permission>())
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    name.value = props.initial?.name ?? ''
    text.value = props.initial?.description ?? ''
    chosen.value = new Set(props.initial?.permissions ?? [])
    error.value = null
  }
})

const choosable = computed(() => props.permissions.filter((permission) => props.grantable.includes(permission)))

function toggle(permission: Permission, on: boolean): void {
  const next = new Set(chosen.value)
  if (on) {
    next.add(permission)
  } else {
    next.delete(permission)
  }
  chosen.value = next
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await props.save({
      name: name.value,
      description: text.value,
      permissions: props.permissions.filter((permission) => chosen.value.has(permission)),
    })
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
    <DialogContent class="max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ $t('roles.createText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="role-name">{{ $t('roles.name') }}</Label>
          <Input id="role-name" v-model="name" maxlength="80" required autofocus />
        </div>
        <div class="grid gap-2">
          <Label for="role-description">{{ $t('roles.descriptionLabel') }}</Label>
          <Textarea id="role-description" v-model="text" maxlength="500" rows="2" />
        </div>
        <div class="grid gap-2">
          <label
            v-for="permission in choosable"
            :key="permission"
            class="flex items-center gap-3 rounded-md border p-2 text-sm"
            :data-test="`permission-${permission}`"
          >
            <Checkbox
              :model-value="chosen.has(permission)"
              @update:model-value="(on) => toggle(permission, on === true)"
            />
            {{ $t(`roles.permissions.${permission}`) }}
          </label>
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !name.trim() || chosen.size === 0" data-test="save-role">
            {{ $t('common.save') }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
