<script setup lang="ts">
import { FileText, Loader2, X } from '@lucide/vue'
import { IMAGE_TYPES, type FileChip } from '@/core/files'
import { formatBytes } from '@/core/format'

/**
 * Files as chips: a link to each (images with a small preview), and for files not sent yet a button that takes them
 * back. `href` gives a file's address; without it the chip is not a link (an upload still running).
 */
defineProps<{ files: FileChip[]; href?: (file: FileChip) => string; removable?: boolean }>()
defineEmits<{ remove: [file: FileChip] }>()
</script>

<template>
  <ul v-if="files.length" class="flex flex-wrap gap-2" data-test="file-chips">
    <li
      v-for="file in files"
      :key="file.id"
      class="flex max-w-full items-center gap-2 rounded-md border bg-background px-2 py-1 text-xs"
      :data-test="`file-${file.filename}`"
    >
      <Loader2 v-if="file.uploading" class="size-4 shrink-0 animate-spin text-muted-foreground" />
      <img
        v-else-if="href && IMAGE_TYPES.includes(file.content_type)"
        :src="href(file)"
        alt=""
        class="size-8 shrink-0 rounded object-cover"
        loading="lazy"
      />
      <FileText v-else class="size-4 shrink-0 text-muted-foreground" />
      <a
        v-if="href && !file.uploading"
        :href="href(file)"
        target="_blank"
        rel="noopener"
        class="truncate font-medium hover:underline"
        :download="IMAGE_TYPES.includes(file.content_type) ? undefined : file.filename"
        >{{ file.filename }}</a
      >
      <span v-else class="truncate font-medium">{{ file.filename }}</span>
      <span class="shrink-0 text-muted-foreground">{{ formatBytes(file.size) }}</span>
      <button
        v-if="removable && !file.uploading"
        type="button"
        class="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        :aria-label="$t('files.remove', { name: file.filename })"
        :data-test="`remove-file-${file.filename}`"
        @click="$emit('remove', file)"
      >
        <X class="size-3.5" />
      </button>
    </li>
  </ul>
</template>
