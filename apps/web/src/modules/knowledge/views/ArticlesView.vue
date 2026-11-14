<script setup lang="ts">
import { BookOpen, Globe, Lock, Pencil, Plus, Search, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDate } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import { useTenants } from '@/modules/tenancy/tenants'
import { knowledgeApi, type Article } from '../api'

/** The knowledge base: internal articles for the team, public ones in the help center. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const manage = computed(() => tenants.can('knowledge.manage'))
const search = ref('')
const category = ref('')
const library = useAsyncData(() =>
  knowledgeApi.articles(tenantId.value, { q: search.value.trim() || undefined, category: category.value || undefined }),
)

const reading = ref<Article | null>(null)
const editing = ref<Article | null>(null)
const dialogOpen = ref(false)
const form = ref<{ title: string; body: string; category: string; tags: string; visibility: 'internal' | 'public' }>({
  title: '',
  body: '',
  category: '',
  tags: '',
  visibility: 'internal',
})
const error = ref<string | null>(null)
const deleting = ref<Article | null>(null)
const deleteOpen = ref(false)

function openDialog(article: Article | null): void {
  editing.value = article
  form.value = {
    title: article?.title ?? '',
    body: article?.body ?? '',
    category: article?.category ?? '',
    tags: (article?.tags ?? []).join(', '),
    visibility: article?.visibility ?? 'internal',
  }
  error.value = null
  dialogOpen.value = true
}

async function save(): Promise<void> {
  error.value = null
  const body = {
    ...form.value,
    tags: form.value.tags
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean),
  }
  try {
    const saved = editing.value
      ? await knowledgeApi.updateArticle(tenantId.value, editing.value.id, body)
      : await knowledgeApi.createArticle(tenantId.value, body)
    notify.success(t('articles.saved', { title: saved.title }))
    dialogOpen.value = false
    reading.value = saved
    await library.reload()
  } catch (caught) {
    error.value = errorText(caught)
  }
}

function askDelete(article: Article): void {
  deleting.value = article
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  await knowledgeApi.deleteArticle(tenantId.value, deleting.value!.id)
  notify.success(t('articles.deleted', { title: deleting.value!.title }))
  reading.value = null
  await library.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('articles.title')" :description="$t('articles.description')">
      <Button v-if="tenants.current.value" variant="outline" as-child>
        <a :href="`/help/${tenantId}`" target="_blank" rel="noopener" data-test="help-center"
          ><Globe class="size-4" /> {{ $t('articles.helpCenter') }}</a
        >
      </Button>
      <Button v-if="manage" data-test="create-article" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('articles.create') }}</Button
      >
    </PageHeader>
    <div class="flex flex-wrap gap-2">
      <form class="relative min-w-56 flex-1" @submit.prevent="library.reload()">
        <Search class="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
        <Input v-model="search" type="search" class="pl-8" :placeholder="$t('articles.search')" data-test="search" />
      </form>
      <NativeSelect
        v-model="category"
        class="w-48"
        :aria-label="$t('articles.category')"
        :options="[
          { value: '', label: $t('articles.allCategories') },
          ...(library.data.value?.categories ?? []).map((each) => ({ value: each, label: each })),
        ]"
        @update:model-value="library.reload()"
      />
    </div>
    <ErrorAlert v-if="library.error.value" :message="library.error.value" />
    <EmptyState
      v-else-if="library.data.value?.articles.length === 0"
      :title="$t('articles.empty')"
      :description="$t('articles.emptyHint')"
    >
      <template #icon><BookOpen class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <div v-else-if="library.data.value" class="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <Card>
        <CardContent class="grid gap-1 pt-6">
          <button
            v-for="article in library.data.value.articles"
            :key="article.id"
            type="button"
            :class="[
              'rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted',
              reading?.id === article.id && 'bg-muted font-medium',
            ]"
            :data-test="`article-${article.id}`"
            @click="reading = article"
          >
            <span class="flex items-center gap-1.5">
              <Globe v-if="article.visibility === 'public'" class="size-3.5 text-muted-foreground" />
              <Lock v-else class="size-3.5 text-muted-foreground" />
              <span class="truncate">{{ article.title }}</span>
            </span>
            <span v-if="article.category" class="block text-xs text-muted-foreground">{{ article.category }}</span>
          </button>
        </CardContent>
      </Card>
      <Card>
        <CardContent class="pt-6">
          <article v-if="reading" class="grid gap-3" data-test="reading">
            <header class="flex items-start justify-between gap-2">
              <div>
                <h2 class="text-xl font-semibold">{{ reading.title }}</h2>
                <p class="text-xs text-muted-foreground">
                  {{ $t(`articles.visibility.${reading.visibility}`) }} · {{ formatDate(reading.updated_at) }}
                  <template v-if="reading.tags.length">
                    · {{ reading.tags.map((tag) => `#${tag}`).join(' ') }}</template
                  >
                </p>
              </div>
              <span v-if="manage" class="flex">
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.edit')"
                  data-test="edit-article"
                  @click="openDialog(reading)"
                  ><Pencil class="size-4"
                /></Button>
                <Button
                  variant="ghost"
                  size="icon"
                  :aria-label="$t('common.delete')"
                  data-test="delete-article"
                  @click="askDelete(reading)"
                  ><Trash2 class="size-4"
                /></Button>
              </span>
            </header>
            <p class="text-sm whitespace-pre-wrap">{{ reading.body }}</p>
          </article>
          <p v-else class="text-sm text-muted-foreground">{{ $t('articles.pick') }}</p>
        </CardContent>
      </Card>
    </div>

    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{{ editing ? $t('articles.edit') : $t('articles.create') }}</DialogTitle>
          <DialogDescription>{{ $t('articles.dialogText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="save">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-2">
            <Label for="article-title">{{ $t('articles.titleLabel') }}</Label>
            <Input id="article-title" v-model="form.title" maxlength="200" required autofocus />
          </div>
          <div class="grid gap-2">
            <Label for="article-body">{{ $t('knowledge.text') }}</Label>
            <Textarea id="article-body" v-model="form.body" rows="10" required />
          </div>
          <div class="grid gap-4 sm:grid-cols-3">
            <div class="grid gap-2">
              <Label for="article-category">{{ $t('articles.category') }}</Label>
              <Input id="article-category" v-model="form.category" maxlength="80" />
            </div>
            <div class="grid gap-2">
              <Label for="article-tags">{{ $t('tickets.tags') }}</Label>
              <Input id="article-tags" v-model="form.tags" />
            </div>
            <div class="grid gap-2">
              <Label for="article-visibility">{{ $t('articles.visibilityLabel') }}</Label>
              <NativeSelect
                id="article-visibility"
                v-model="form.visibility"
                :options="
                  (['internal', 'public'] as const).map((value) => ({
                    value,
                    label: $t(`articles.visibility.${value}`),
                  }))
                "
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" data-test="save-article">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('articles.deleteTitle', { title: deleting?.title })"
      :description="$t('articles.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
