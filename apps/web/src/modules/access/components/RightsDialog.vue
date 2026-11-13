<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/core/ui/button'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import type { QueueRight } from '../api'

/** The rights of one group in one queue, one by one, for what no ready-made level fits. */
const props = defineProps<{ title: string; all: QueueRight[]; rights: QueueRight[] }>()
const emit = defineEmits<{ save: [rights: QueueRight[]] }>()
const open = defineModel<boolean>('open', { default: false })

const chosen = ref(new Set<QueueRight>())

watch(open, (opened) => {
  if (opened) {
    chosen.value = new Set(props.rights)
  }
})

function toggle(right: QueueRight, on: boolean): void {
  const next = new Set(chosen.value)
  if (on) {
    next.add(right)
  } else {
    next.delete(right)
  }
  chosen.value = next
}

function submit(): void {
  emit(
    'save',
    props.all.filter((right) => chosen.value.has(right)),
  )
  open.value = false
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ $t('access.rights.customText') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-2" @submit.prevent="submit">
        <label
          v-for="right in all"
          :key="right"
          class="flex items-start gap-3 rounded-md border p-2 text-sm"
          :data-test="`right-${right}`"
        >
          <Checkbox
            class="mt-0.5"
            :model-value="chosen.has(right)"
            @update:model-value="(on) => toggle(right, on === true)"
          />
          <span>
            <span class="font-medium">{{ $t(`access.rights.names.${right}`) }}</span>
            <span class="block text-xs text-muted-foreground">{{ $t(`access.rights.hints.${right}`) }}</span>
          </span>
        </label>
        <DialogFooter>
          <Button type="submit" data-test="save-rights">{{ $t('common.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
