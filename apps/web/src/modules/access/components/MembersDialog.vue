<script setup lang="ts">
import { ref, watch } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import type { Member } from '@/modules/tenancy/api'
import { accessApi, type Group } from '../api'

/** Who is in a group: a tick for each member of the organization. */
const props = defineProps<{ tenantId: string; group: Group | null; members: Member[] }>()
const emit = defineEmits<{ saved: [group: Group] }>()
const open = defineModel<boolean>('open', { default: false })

const chosen = ref(new Set<string>())
const error = ref<string | null>(null)
const busy = ref(false)

watch(open, (opened) => {
  if (opened) {
    chosen.value = new Set(props.group?.member_ids ?? [])
    error.value = null
  }
})

function toggle(userId: string, on: boolean): void {
  const next = new Set(chosen.value)
  if (on) {
    next.add(userId)
  } else {
    next.delete(userId)
  }
  chosen.value = next
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    const group = await accessApi.setMembers(props.tenantId, props.group!.id, [...chosen.value])
    emit('saved', group)
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
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ $t('access.groups.membersTitle', { name: group?.name }) }}</DialogTitle>
        <DialogDescription>{{ $t('access.groups.membersText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid max-h-80 gap-2 overflow-y-auto">
          <label
            v-for="member in members"
            :key="member.user_id"
            class="flex items-center gap-3 rounded-md border p-2 text-sm"
            :data-test="`member-${member.email}`"
          >
            <Checkbox
              :model-value="chosen.has(member.user_id)"
              @update:model-value="(on) => toggle(member.user_id, on === true)"
            />
            <span class="min-w-0 truncate">{{ member.email }}</span>
            <span class="ml-auto text-xs text-muted-foreground">{{ $t(`tenant.roles.${member.role}`) }}</span>
          </label>
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy" data-test="save-members">{{ $t('common.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
