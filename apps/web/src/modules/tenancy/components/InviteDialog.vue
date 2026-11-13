<script setup lang="ts">
import { UserPlus } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { tenancyApi, type TenantRole } from '../api'
import { useRoles } from '../roles'
import { useTenants } from '../tenants'

const emit = defineEmits<{ invited: [] }>()

const { t } = useI18n()
const tenants = useTenants()
const open = ref(false)
const email = ref('')
const role = ref<TenantRole>('agent')
const error = ref<string | null>(null)
const busy = ref(false)

/** Only roles that may not do more than the inviter (so only owners invite owners). */
const known = useRoles()
const roles = computed(() =>
  known.assignable().map((each) => ({
    value: each.id,
    label: `${known.label(each.id)} – ${each.builtin ? t(`tenant.roleDescriptions.${each.id}`) : each.description}`,
  })),
)

watch(open, () => {
  if (open.value) {
    void known.load().catch(() => undefined)
  }
  email.value = ''
  role.value = 'agent'
  error.value = null
})

async function submit(): Promise<void> {
  const tenant = tenants.current.value
  if (!tenant) {
    return
  }
  busy.value = true
  error.value = null
  try {
    const invitation = await tenancyApi.invite(tenant.id, { email: email.value, role: role.value })
    notify.success(t('team.invited', { email: invitation.email }))
    open.value = false
    emit('invited')
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogTrigger as-child>
      <Button data-test="invite"><UserPlus class="size-4" /> {{ $t('team.invite') }}</Button>
    </DialogTrigger>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ $t('team.inviteTitle') }}</DialogTitle>
        <DialogDescription>{{ $t('team.inviteText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="submit">
        <ErrorAlert v-if="error" :message="error" />
        <div class="grid gap-2">
          <Label for="invite-email">{{ $t('common.email') }}</Label>
          <Input id="invite-email" v-model="email" type="email" required autofocus />
        </div>
        <div class="grid gap-2">
          <Label for="invite-role">{{ $t('common.role') }}</Label>
          <NativeSelect id="invite-role" v-model="role" :options="roles" />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="busy || !email" data-test="invite-submit">
            {{ $t('team.inviteSubmit') }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
