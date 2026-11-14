<script setup lang="ts">
import { ArrowLeft, Paperclip } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import FileChips from '@/core/components/FileChips.vue'
import type { FileChip } from '@/core/files'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDateTime } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { cn } from '@/core/lib/utils'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Textarea } from '@/core/ui/textarea'
import { portalApi } from '../api'

/** One ticket in the portal: the public conversation (never internal notes) and a reply. */
const route = useRoute()
const tenantId = computed(() => String(route.params.tenantId))
const ticketId = computed(() => String(route.params.ticketId))
const thread = useAsyncData(() => portalApi.thread(tenantId.value, ticketId.value))
const body = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
/** Up to five files go with the reply. */
const MAX_FILES = 5
const files = ref<File[]>([])
const picker = ref<HTMLInputElement | null>(null)
const chips = computed<FileChip[]>(() =>
  files.value.map((file, index) => ({
    id: String(index),
    filename: file.name,
    content_type: file.type,
    size: file.size,
  })),
)
function pick(list: FileList | null): void {
  files.value = [...files.value, ...Array.from(list ?? [])].slice(0, MAX_FILES)
  if (picker.value) {
    picker.value.value = ''
  }
}
function unpick(chip: FileChip): void {
  files.value = files.value.filter((_file, index) => String(index) !== chip.id)
}
const fileUrl = (file: FileChip) => portalApi.fileUrl(tenantId.value, ticketId.value, file.id)

async function answer(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    thread.data.value = await portalApi.answer(tenantId.value, ticketId.value, body.value, files.value)
    body.value = ''
    files.value = []
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto grid max-w-3xl gap-6 p-4 md:p-8">
    <RouterLink
      :to="{ name: 'portal', params: { tenantId } }"
      class="flex items-center gap-1 text-sm text-muted-foreground"
      data-test="portal-back"
      ><ArrowLeft class="size-4" /> {{ $t('portal.allTickets') }}</RouterLink
    >
    <ErrorAlert v-if="thread.error.value" :message="thread.error.value" />
    <template v-else-if="thread.data.value">
      <header class="flex flex-wrap items-center gap-3">
        <h1 class="text-2xl font-semibold" data-test="portal-subject-title">
          <span class="text-muted-foreground tabular-nums">#{{ thread.data.value.ticket.number }}</span>
          {{ thread.data.value.ticket.subject }}
        </h1>
        <Badge variant="outline">{{ $t(`portal.states.${thread.data.value.ticket.state}`) }}</Badge>
      </header>
      <ol class="grid gap-3">
        <li
          v-for="message in thread.data.value.messages"
          :key="message.id"
          :class="cn('grid gap-1 rounded-lg border p-3', message.from_customer ? 'ml-8 bg-muted/50' : 'mr-8')"
          :data-test="`portal-message-${message.id}`"
        >
          <p class="flex gap-2 text-xs text-muted-foreground">
            <span class="font-medium text-foreground">{{
              message.from_customer ? $t('portal.you') : message.author_name
            }}</span>
            <span>{{ formatDateTime(message.created_at) }}</span>
          </p>
          <p v-if="message.body" class="whitespace-pre-wrap">{{ message.body }}</p>
          <FileChips :files="message.attachments" :href="fileUrl" />
        </li>
      </ol>
      <form class="grid gap-3" @submit.prevent="answer">
        <ErrorAlert v-if="error" :message="error" />
        <Textarea v-model="body" rows="4" :placeholder="$t('portal.replyPlaceholder')" data-test="portal-reply" />
        <p v-if="thread.data.value.ticket.state === 'closed'" class="text-xs text-muted-foreground">
          {{ $t('portal.reopens') }}
        </p>
        <FileChips :files="chips" removable @remove="unpick" />
        <div class="flex flex-wrap items-center gap-2">
          <input
            ref="picker"
            type="file"
            multiple
            class="hidden"
            data-test="portal-file-input"
            @change="pick(($event.target as HTMLInputElement).files)"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            class="gap-1"
            :disabled="files.length >= MAX_FILES"
            data-test="portal-attach"
            @click="picker?.click()"
            ><Paperclip class="size-4" />{{ $t('portal.attach', { count: MAX_FILES }) }}</Button
          >
          <Button
            type="submit"
            class="ml-auto"
            :disabled="busy || (!body.trim() && !files.length)"
            data-test="portal-answer"
            >{{ $t('portal.send') }}</Button
          >
        </div>
      </form>
    </template>
  </div>
</template>
