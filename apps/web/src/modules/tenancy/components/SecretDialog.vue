<script setup lang="ts">
import { Copy } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'

/** A secret right after it was made (an API key): the only time anyone sees it. */
const props = defineProps<{ secret: string | null; title?: string; text?: string }>()
const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.secret!)
    notify.success(t('apiKeys.copied'))
  } catch (caught) {
    notify.error(caught)
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ title ?? $t('apiKeys.secretTitle') }}</DialogTitle>
        <DialogDescription>{{ text ?? $t('apiKeys.secretText') }}</DialogDescription>
      </DialogHeader>
      <div class="flex items-center gap-2">
        <code class="min-w-0 flex-1 rounded-md border bg-muted px-3 py-2 text-sm break-all" data-test="secret">{{
          secret
        }}</code>
        <Button variant="outline" size="icon" :aria-label="$t('apiKeys.copy')" data-test="copy" @click="copy">
          <Copy class="size-4" />
        </Button>
      </div>
      <DialogFooter>
        <Button data-test="secret-done" @click="open = false">{{ $t('common.close') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
