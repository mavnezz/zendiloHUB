<script setup lang="ts">
import { ref, watch } from 'vue'
import { notify } from '@/core/notify'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/core/ui/alert-dialog'
import { Button } from '@/core/ui/button'

const props = withDefaults(
  defineProps<{
    title: string
    description: string
    confirmLabel: string
    destructive?: boolean
    /** E.g. until the user typed the name of what they delete. */
    blocked?: boolean
    action: () => Promise<unknown>
  }>(),
  { destructive: true },
)
const open = defineModel<boolean>('open', { default: false })
const busy = ref(false)

watch(open, () => {
  busy.value = false
})

async function confirm(): Promise<void> {
  busy.value = true
  try {
    await props.action()
    open.value = false
  } catch (caught) {
    notify.error(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AlertDialog v-model:open="open">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ title }}</AlertDialogTitle>
        <AlertDialogDescription>{{ description }}</AlertDialogDescription>
      </AlertDialogHeader>
      <slot />
      <AlertDialogFooter>
        <AlertDialogCancel :disabled="busy">{{ $t('common.cancel') }}</AlertDialogCancel>
        <Button
          :variant="destructive ? 'destructive' : 'default'"
          :disabled="busy || blocked"
          data-test="confirm"
          @click="confirm"
        >
          {{ confirmLabel }}
        </Button>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
