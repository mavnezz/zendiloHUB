<script setup lang="ts">
import {
  AlertTriangle,
  Check,
  Clock,
  Lock,
  LockKeyhole,
  Mail,
  Phone,
  RotateCcw,
  Scissors,
  ShieldAlert,
  ShieldCheck,
} from '@lucide/vue'
import { ref } from 'vue'
import FileChips from '@/core/components/FileChips.vue'
import { formatDateTime } from '@/core/format'
import { cn } from '@/core/lib/utils'
import { Button } from '@/core/ui/button'
import type { Delivery } from '@/modules/channels/api'
import type { CustomerCard, TicketMessage } from '../api'

/**
 * The messages of a ticket, oldest first: the customer's on the left, the team's on the right, notes in yellow.
 * Replies show whether they went out by e-mail; received e-mails can be shown formatted (their HTML was cleaned).
 */
defineProps<{
  messages: TicketMessage[]
  fileUrl?: (messageId: string, fileId: string) => string
  customer: CustomerCard | null
  canSplit: boolean
  deliveries?: Record<string, Delivery>
}>()
defineEmits<{ split: [message: TicketMessage]; resend: [message: TicketMessage] }>()

const formatted = ref(new Set<string>())
function toggle(id: string): void {
  const next = new Set(formatted.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  formatted.value = next
}
</script>

<template>
  <ol class="grid gap-4">
    <li
      v-for="message in messages"
      :key="message.id"
      :class="cn('flex', message.direction === 'out' ? 'justify-end' : 'justify-start')"
      :data-test="`message-${message.kind}-${message.direction}`"
    >
      <article
        :class="
          cn(
            'group w-full max-w-[85%] rounded-lg border p-4 shadow-xs',
            message.kind === 'internal' && 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30',
            message.kind === 'public' && message.direction === 'out' && 'bg-primary/5',
          )
        "
      >
        <header class="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <Lock v-if="message.kind === 'internal'" class="size-3.5" />
          <Phone v-else-if="message.direction === 'in' && !message.from_address" class="size-3.5" />
          <Mail v-else-if="message.from_address" class="size-3.5" />
          <span class="font-medium text-foreground">
            {{
              message.author_kind === 'customer'
                ? (customer?.name ?? message.from_address ?? $t('tickets.theCustomer'))
                : message.author_name
            }}
          </span>
          <span>{{ $t(`tickets.messageKinds.${message.kind === 'internal' ? 'note' : message.direction}`) }}</span>
          <time :datetime="message.created_at">{{ formatDateTime(message.created_at) }}</time>
          <span v-if="message.direction === 'in' && message.from_address" class="truncate">{{
            message.from_address
          }}</span>
          <span
            v-if="message.security"
            :class="
              cn(
                'flex items-center gap-1',
                message.security.signature === 'valid' && 'text-emerald-600 dark:text-emerald-400',
                message.security.signature && message.security.signature !== 'valid' && 'text-amber-600',
                message.security.signature === 'invalid' && 'text-destructive',
              )
            "
            :title="
              message.security.signer
                ? $t('tickets.security.signer', { address: message.security.signer })
                : $t(`tickets.security.hint`)
            "
            :data-test="`security-${message.id}`"
          >
            <ShieldCheck v-if="message.security.signature === 'valid'" class="size-3.5" />
            <ShieldAlert v-else-if="message.security.signature" class="size-3.5" />
            <LockKeyhole v-if="message.security.encrypted" class="size-3.5" />
            <span v-if="message.security.signature">{{
              $t(`tickets.security.signature.${message.security.signature}`)
            }}</span>
            <span v-if="message.security.encrypted">{{ $t('tickets.security.encrypted') }}</span>
          </span>
          <template v-if="deliveries?.[message.id]">
            <span
              v-for="delivery in [deliveries[message.id]!]"
              :key="delivery.status"
              :class="
                cn(
                  'flex items-center gap-1',
                  delivery.status === 'sent' && 'text-emerald-600 dark:text-emerald-400',
                  delivery.status === 'failed' && 'text-destructive',
                )
              "
              :title="delivery.error ?? undefined"
              :data-test="`delivery-${message.id}`"
            >
              <Check v-if="delivery.status === 'sent'" class="size-3.5" />
              <Clock v-else-if="delivery.status === 'queued'" class="size-3.5" />
              <AlertTriangle v-else class="size-3.5" />
              {{
                delivery.status === 'skipped'
                  ? $t(`tickets.delivery.skipped.${delivery.error ?? 'no_account'}`)
                  : delivery.status === 'failed' && delivery.error?.startsWith('smime_')
                    ? $t(`tickets.delivery.smime.${delivery.error}`)
                    : $t(`tickets.delivery.${delivery.status}`)
              }}
              <Button
                v-if="delivery.status === 'failed'"
                variant="ghost"
                size="icon"
                class="size-5"
                :aria-label="$t('tickets.delivery.resend')"
                :data-test="`resend-${message.id}`"
                @click="$emit('resend', message)"
                ><RotateCcw class="size-3"
              /></Button>
            </span>
          </template>
          <Button
            v-if="canSplit"
            variant="ghost"
            size="icon"
            class="ml-auto size-6 opacity-0 group-hover:opacity-100 focus:opacity-100"
            :aria-label="$t('tickets.split')"
            :data-test="`split-${message.id}`"
            @click="$emit('split', message)"
            ><Scissors class="size-3.5"
          /></Button>
        </header>
        <!-- The HTML of received e-mails was cleaned on the server (no scripts, styles or outside images). -->
        <!-- eslint-disable vue/no-v-html -->
        <div
          v-if="message.body_html && formatted.has(message.id)"
          class="prose-sm text-sm"
          v-html="message.body_html"
        />
        <p v-else-if="message.body" class="text-sm break-words whitespace-pre-wrap">{{ message.body }}</p>
        <!-- eslint-enable vue/no-v-html -->
        <FileChips
          :files="message.attachments"
          :href="fileUrl ? (file) => fileUrl!(message.id, file.id) : undefined"
          class="mt-3"
        />
        <button
          v-if="message.body_html"
          type="button"
          class="mt-2 text-xs text-muted-foreground underline"
          :data-test="`formatted-${message.id}`"
          @click="toggle(message.id)"
        >
          {{ formatted.has(message.id) ? $t('tickets.showPlain') : $t('tickets.showFormatted') }}
        </button>
      </article>
    </li>
  </ol>
</template>
