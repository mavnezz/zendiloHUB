<script setup lang="ts">
import { Lock, Phone, Scissors } from '@lucide/vue'
import { formatDateTime } from '@/core/format'
import { cn } from '@/core/lib/utils'
import { Button } from '@/core/ui/button'
import type { CustomerCard, TicketMessage } from '../api'

/** The messages of a ticket, oldest first: the customer's on the left, the team's on the right, notes in yellow. */
defineProps<{ messages: TicketMessage[]; customer: CustomerCard | null; canSplit: boolean }>()
defineEmits<{ split: [message: TicketMessage] }>()
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
          <span class="font-medium text-foreground">
            {{
              message.author_kind === 'customer'
                ? (customer?.name ?? message.from_address ?? $t('tickets.theCustomer'))
                : message.author_name
            }}
          </span>
          <span>{{ $t(`tickets.messageKinds.${message.kind === 'internal' ? 'note' : message.direction}`) }}</span>
          <time :datetime="message.created_at">{{ formatDateTime(message.created_at) }}</time>
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
        <p class="text-sm break-words whitespace-pre-wrap">{{ message.body }}</p>
      </article>
    </li>
  </ol>
</template>
