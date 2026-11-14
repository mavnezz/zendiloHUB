<script setup lang="ts">
import { BellOff, BellRing } from '@lucide/vue'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { useFollowedQueues } from '../followed'

/** In a queue's inbox: follow the queue (hear about its new tickets) or stop following it. */
const props = defineProps<{ queueId: string; queueName: string }>()
const { t } = useI18n()
const followed = useFollowedQueues()
const following = computed(() => followed.modeOf(props.queueId) !== null)

onMounted(() => void followed.load().catch(() => undefined))

async function toggle(): Promise<void> {
  try {
    await followed.set(props.queueId, following.value ? null : 'new')
    notify.success(
      t(following.value ? 'notifications.followed.on' : 'notifications.followed.off', { queue: props.queueName }),
    )
  } catch (caught) {
    notify.error(caught)
  }
}
</script>

<template>
  <Button
    variant="outline"
    size="sm"
    :aria-pressed="following"
    :title="$t('notifications.followed.hint')"
    data-test="follow-queue"
    @click="toggle"
  >
    <component :is="following ? BellRing : BellOff" class="size-4" />
    {{ following ? $t('notifications.followed.following') : $t('notifications.followed.follow') }}
  </Button>
</template>
