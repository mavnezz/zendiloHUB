<script setup lang="ts">
import {
  ArrowRightLeft,
  AtSign,
  Bell,
  FilePlus,
  Inbox,
  ListChecks,
  MessageSquare,
  TimerOff,
  UserCheck,
} from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { formatDateTime } from '@/core/format'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/core/ui/dropdown-menu'
import { Switch } from '@/core/ui/switch'
import { useTenants } from '@/modules/tenancy/tenants'
import { notificationsApi, type Notification } from '../api'
import FollowedQueuesDialog from './FollowedQueuesDialog.vue'

/** The bell in the header: what happened in the caller's tickets, checked every half minute. */
const POLL_MS = 30_000
const ICONS = {
  assigned: UserCheck,
  mentioned: AtSign,
  message: MessageSquare,
  sla_breached: TimerOff,
  created: FilePlus,
  moved: ArrowRightLeft,
} as const

const tenants = useTenants()
const tenantId = computed(() => tenants.current.value?.id)
const items = ref<Notification[]>([])
const unread = ref(0)
const email = ref(false)
const followOpen = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

async function load(): Promise<void> {
  if (!tenantId.value || tenants.current.value?.role === null) {
    return
  }
  try {
    const inbox = await notificationsApi.list(tenantId.value)
    items.value = inbox.items
    unread.value = inbox.unread
  } catch {
    // Offline for a moment: the next round tries again.
  }
}

async function opened(open: boolean): Promise<void> {
  if (open && tenantId.value) {
    email.value = (await notificationsApi.settings(tenantId.value).catch(() => ({ email: false }))).email
  }
}

async function readAll(): Promise<void> {
  const inbox = await notificationsApi.read(tenantId.value!)
  items.value = inbox.items
  unread.value = inbox.unread
}

async function readOne(item: Notification): Promise<void> {
  if (!item.read_at) {
    const inbox = await notificationsApi.read(tenantId.value!, [item.id]).catch(() => null)
    if (inbox) {
      items.value = inbox.items
      unread.value = inbox.unread
    }
  }
}

async function setEmail(on: boolean): Promise<void> {
  try {
    email.value = (await notificationsApi.saveSettings(tenantId.value!, on)).email
  } catch (caught) {
    notify.error(caught)
  }
}

onMounted(() => {
  void load()
  timer = setInterval(() => void load(), POLL_MS)
})
onUnmounted(() => clearInterval(timer))
defineExpose({ load })
</script>

<template>
  <DropdownMenu @update:open="opened">
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="icon" class="relative" :aria-label="$t('notifications.title')" data-test="bell">
        <Bell class="size-4" />
        <span
          v-if="unread"
          class="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground"
          data-test="unread"
          >{{ unread > 99 ? '99+' : unread }}</span
        >
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-96 p-0">
      <div class="flex items-center justify-between border-b px-3 py-2">
        <span class="text-sm font-medium">{{ $t('notifications.title') }}</span>
        <Button v-if="unread" variant="ghost" size="sm" class="h-7 text-xs" data-test="read-all" @click="readAll">
          {{ $t('notifications.readAll') }}
        </Button>
      </div>
      <div class="max-h-96 overflow-y-auto">
        <p v-if="!items.length" class="flex items-center gap-2 p-4 text-sm text-muted-foreground">
          <Inbox class="size-4" /> {{ $t('notifications.empty') }}
        </p>
        <RouterLink
          v-for="item in items"
          :key="item.id"
          :to="{ name: 'ticket', params: { tenantId, ticketId: item.ticket_id } }"
          :class="[
            'flex gap-3 border-b px-3 py-2 text-sm last:border-0 hover:bg-muted',
            !item.read_at && 'bg-primary/5',
          ]"
          :data-test="`notification-${item.id}`"
          @click="readOne(item)"
        >
          <component :is="ICONS[item.kind]" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0">
            <span class="block truncate font-medium">#{{ item.ticket_number }} {{ item.subject }}</span>
            <span class="block truncate text-xs text-muted-foreground">
              {{ $t(`notifications.kinds.${item.kind}`, { actor: item.actor }) }} ·
              {{ formatDateTime(item.created_at) }}
            </span>
          </span>
        </RouterLink>
      </div>
      <label class="flex items-center gap-3 border-t px-3 py-2 text-xs">
        <Switch :model-value="email" data-test="email-notifications" @update:model-value="setEmail" />
        {{ $t('notifications.email') }}
      </label>
      <button
        type="button"
        class="flex w-full items-center gap-3 border-t px-3 py-2 text-left text-xs hover:bg-muted"
        data-test="followed-queues"
        @click="followOpen = true"
      >
        <ListChecks class="size-4 text-muted-foreground" /> {{ $t('notifications.followed.manage') }}
      </button>
    </DropdownMenuContent>
  </DropdownMenu>
  <FollowedQueuesDialog v-model:open="followOpen" />
</template>
