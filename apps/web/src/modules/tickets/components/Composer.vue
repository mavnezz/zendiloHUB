<script setup lang="ts">
import { Paperclip } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import FileChips from '@/core/components/FileChips.vue'
import type { FileChip } from '@/core/files'
import NativeSelect from '@/core/components/NativeSelect.vue'
import SegmentedControl from '@/core/components/SegmentedControl.vue'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import {
  fromLocalInput,
  PENDING_STATES,
  SETTABLE_STATES,
  ticketsApi,
  type MessageRequest,
  type TicketDetail,
} from '../api'
import { channelsApi } from '@/modules/channels/api'
import { fill, knowledgeApi, type Article, type TextModule } from '@/modules/knowledge/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { useAssistant } from '../assistant'
import { useDirectory } from '../directory'

/**
 * Writing in a ticket: a reply to the customer, an internal note (`@name` makes a member watch the ticket) or what the
 * customer said on the phone; the state can change along with it, and the time spent is recorded.
 */
const props = defineProps<{ ticket: TicketDetail }>()
const emit = defineEmits<{ sent: []; writing: [busy: boolean] }>()

type Mode = 'reply' | 'note' | 'customer'

const { t } = useI18n()
const directory = useDirectory()
const tenants = useTenants()
const rights = computed(() => props.ticket.rights)
const modes = computed(() =>
  (['reply', 'note', 'customer'] as const)
    .filter((mode) => rights.value.includes(mode === 'note' ? 'note' : 'reply'))
    .map((value) => ({ value, label: t(`tickets.composer.${value}`) })),
)
const mode = ref<Mode>('reply')
const body = ref('')
const state = ref('')
const pendingUntil = ref('')
const minutes = ref('')
const busy = ref(false)

watch(
  modes,
  (options) => {
    if (!options.some((option) => option.value === mode.value) && options[0]) {
      mode.value = options[0].value
    }
  },
  { immediate: true },
)

/** A reply starts with the queue's salutation and signature (with the writer's details filled in). */
const draft = ref('')
async function loadDraft(): Promise<void> {
  const ticket = props.ticket
  try {
    const answer = await channelsApi.replyDraft(tenants.current.value!.id, ticket.queue_id, {
      number: ticket.number,
      subject: ticket.subject,
      customer_name: ticket.customer?.name ?? '',
      customer_email: ticket.customer?.email ?? '',
    })
    draft.value = answer.text
  } catch {
    draft.value = ''
  }
  if (mode.value === 'reply' && !body.value.trim()) {
    body.value = draft.value
  }
}
onMounted(loadDraft)
watch(mode, (next, before) => {
  if (next === 'reply' && (!body.value.trim() || body.value === draft.value)) {
    body.value = draft.value
  } else if (before === 'reply' && body.value === draft.value) {
    body.value = ''
  }
})

const stateOptions = computed(() => [
  { value: '', label: t('tickets.composer.keepState') },
  ...SETTABLE_STATES.map((value) => ({ value, label: t(`tickets.states.${value}`) })),
])
const pending = computed(() => PENDING_STATES.includes(state.value as never))

/** Text modules: `::keyword` at the end of the text offers the matching ones; picking one puts it in its place. */
const modules = ref<TextModule[]>([])
onMounted(async () => {
  modules.value = await knowledgeApi.textModules(tenants.current.value!.id, props.ticket.queue_id).catch(() => [])
})
const typed = computed(() => /(?:^|\s)::([\w-]*)$/.exec(body.value)?.[1])
const suggestions = computed(() =>
  typed.value === undefined
    ? []
    : modules.value.filter((module) => module.keyword.startsWith(typed.value!.toLowerCase())).slice(0, 6),
)
function insert(module: TextModule): void {
  const ticket = props.ticket
  const text = fill(module.body, {
    'customer.name': ticket.customer?.name ?? '',
    'customer.email': ticket.customer?.email ?? '',
    'ticket.number': String(ticket.number),
    'ticket.subject': ticket.subject,
  })
  body.value = body.value.replace(/::[\w-]*$/, text)
}
watch(body, (text) => emit('writing', !!text.trim() && text !== draft.value))

/** Articles of the knowledge base, searched and put into the text. */
const articleSearch = ref<string | null>(null)
const articles = ref<Article[]>([])
async function findArticles(): Promise<void> {
  const query = articleSearch.value?.trim()
  articles.value = query
    ? (await knowledgeApi.articles(tenants.current.value!.id, { q: query }).catch(() => ({ articles: [] }))).articles
    : []
}
/** The AI assistant drafts the reply; the agent reads and changes it before sending. */
const assistant = useAssistant(tenants.current.value!.id)
const drafting = ref(false)
async function draftWithAi(): Promise<void> {
  drafting.value = true
  try {
    const answer = await ticketsApi.assist(tenants.current.value!.id, props.ticket.id, 'reply')
    body.value =
      !body.value.trim() || body.value === draft.value ? answer.text : `${body.value.trimEnd()}\n\n${answer.text}`
  } catch (caught) {
    notify.error(caught)
  } finally {
    drafting.value = false
  }
}

function insertArticle(article: Article): void {
  body.value = body.value ? `${body.value.replace(/\s+$/, '')}\n\n${article.body}` : article.body
  articleSearch.value = null
  articles.value = []
}

/** `@bob` or `@bob@example.org` in a note: members to notify. */
function mentions(text: string): string[] {
  const names = [...text.matchAll(/@([\w.+-]+(?:@[\w.-]+)?)/g)].map((match) => (match[1] ?? '').toLowerCase())
  return directory.members.value
    .filter((member) => names.some((name) => member.email === name || member.email.split('@')[0] === name))
    .map((member) => member.user_id)
}

/** Files go up as soon as they are picked or dropped; the message takes them when it is sent. */
const files = ref<FileChip[]>([])
const picker = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const uploading = computed(() => files.value.some((file) => file.uploading))
let pendingUploads = 0

async function attach(list: FileList | File[] | null | undefined): Promise<void> {
  for (const file of Array.from(list ?? [])) {
    const chip: FileChip = {
      id: `upload-${++pendingUploads}`,
      filename: file.name,
      content_type: file.type,
      size: file.size,
      uploading: true,
    }
    files.value = [...files.value, chip]
    try {
      const uploaded = await ticketsApi.upload(tenants.current.value!.id, props.ticket.id, file)
      files.value = files.value.map((each) => (each.id === chip.id ? uploaded : each))
    } catch (caught) {
      files.value = files.value.filter((each) => each.id !== chip.id)
      notify.error(caught)
    }
  }
  if (picker.value) {
    picker.value.value = ''
  }
}

function drop(event: DragEvent): void {
  dragging.value = false
  void attach(event.dataTransfer?.files)
}

async function detach(file: FileChip): Promise<void> {
  files.value = files.value.filter((each) => each.id !== file.id)
  await ticketsApi.discard(tenants.current.value!.id, props.ticket.id, file.id).catch(() => undefined)
}

const empty = computed(() => !files.value.length && (!body.value.trim() || body.value === draft.value))

async function send(): Promise<void> {
  busy.value = true
  const request: MessageRequest = {
    kind: mode.value === 'note' ? 'internal' : 'public',
    direction: mode.value === 'customer' ? 'in' : 'out',
    body: body.value,
    mentions: mode.value === 'note' ? mentions(body.value) : [],
  }
  if (files.value.length) {
    request.attachment_ids = files.value.map((file) => file.id)
  }
  if (state.value) {
    request.state = state.value as MessageRequest['state']
    request.pending_until = pending.value ? fromLocalInput(pendingUntil.value) : null
  }
  if (Number(minutes.value) > 0) {
    request.time_minutes = Math.round(Number(minutes.value))
  }
  try {
    await ticketsApi.addMessage(tenants.current.value!.id, props.ticket.id, request)
    notify.success(t(`tickets.composer.sent.${mode.value}`))
    body.value = mode.value === 'reply' ? draft.value : ''
    state.value = ''
    pendingUntil.value = ''
    minutes.value = ''
    files.value = []
    emit('sent')
  } catch (caught) {
    notify.error(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form
    v-if="modes.length"
    :class="['grid gap-3 rounded-lg border p-4', dragging && 'border-primary bg-primary/5']"
    data-test="composer"
    @submit.prevent="send"
    @dragover.prevent="dragging = true"
    @dragleave.self="dragging = false"
    @drop.prevent="drop"
  >
    <SegmentedControl v-model="mode" :options="modes" :label="$t('tickets.composer.label')" />
    <Textarea
      v-model="body"
      rows="5"
      :placeholder="$t(`tickets.composer.placeholder.${mode}`)"
      :class="mode === 'note' ? 'bg-amber-50 dark:bg-amber-950/30' : ''"
      data-test="composer-body"
    />
    <FileChips :files="files" removable @remove="detach" />
    <div class="flex flex-wrap items-center gap-2">
      <input
        ref="picker"
        type="file"
        multiple
        class="hidden"
        data-test="file-input"
        @change="attach(($event.target as HTMLInputElement).files)"
      />
      <Button
        type="button"
        variant="ghost"
        size="sm"
        class="h-7 gap-1 px-2 text-xs"
        :title="$t('files.dropHint')"
        data-test="attach"
        @click="picker?.click()"
        ><Paperclip class="size-3.5" />{{ $t('files.attach') }}</Button
      >
      <Button
        type="button"
        variant="ghost"
        size="sm"
        class="h-7 px-2 text-xs"
        data-test="find-article"
        @click="articleSearch = articleSearch === null ? '' : null"
        >{{ $t('tickets.composer.article') }}</Button
      >
      <Button
        v-if="assistant && mode === 'reply'"
        type="button"
        variant="ghost"
        size="sm"
        class="h-7 px-2 text-xs"
        :disabled="drafting"
        data-test="draft-ai"
        @click="draftWithAi"
        >{{ drafting ? $t('tickets.assist.working') : $t('tickets.assist.draft') }}</Button
      >
      <form v-if="articleSearch !== null" class="flex flex-1 gap-1" @submit.prevent="findArticles">
        <Input
          v-model="articleSearch"
          class="h-7 text-xs"
          :placeholder="$t('articles.search')"
          data-test="article-search"
        />
      </form>
    </div>
    <div v-if="articles.length" class="grid gap-1" data-test="article-results">
      <button
        v-for="article in articles"
        :key="article.id"
        type="button"
        class="rounded-md border px-2 py-1 text-left text-xs hover:bg-muted"
        :data-test="`insert-article-${article.id}`"
        @click="insertArticle(article)"
      >
        {{ article.title }}
      </button>
    </div>
    <div v-if="suggestions.length" class="flex flex-wrap gap-1" data-test="suggestions">
      <button
        v-for="module in suggestions"
        :key="module.id"
        type="button"
        class="rounded-md border px-2 py-1 text-xs hover:bg-muted"
        :data-test="`suggest-${module.keyword}`"
        @click="insert(module)"
      >
        <code>::{{ module.keyword }}</code> {{ module.name }}
      </button>
    </div>
    <div class="flex flex-wrap items-end gap-3">
      <div v-if="rights.includes('edit')" class="grid gap-1">
        <Label for="composer-state" class="text-xs">{{ $t('tickets.composer.stateAfter') }}</Label>
        <NativeSelect id="composer-state" v-model="state" :options="stateOptions" class="w-48" />
      </div>
      <div v-if="pending" class="grid gap-1">
        <Label for="composer-pending" class="text-xs">{{ $t('tickets.pendingUntil') }}</Label>
        <Input id="composer-pending" v-model="pendingUntil" type="datetime-local" class="w-56" required />
      </div>
      <div class="grid gap-1">
        <Label for="composer-minutes" class="text-xs">{{ $t('tickets.composer.minutes') }}</Label>
        <Input id="composer-minutes" v-model="minutes" type="number" min="1" max="1440" class="w-24" />
      </div>
      <Button type="submit" class="ml-auto" :disabled="busy || uploading || empty" data-test="send">
        {{ $t(`tickets.composer.send.${mode}`) }}
      </Button>
    </div>
  </form>
</template>
