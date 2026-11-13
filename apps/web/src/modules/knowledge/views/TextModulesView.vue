<script setup lang="ts">
import { BookText, Pencil, Plus, Trash2 } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import EmptyState from '@/core/components/EmptyState.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Checkbox } from '@/core/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/core/ui/dialog'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import { accessApi } from '@/modules/access/api'
import { useTenants } from '@/modules/tenancy/tenants'
import { knowledgeApi, type TextModule } from '../api'

/** Texts agents insert with `::keyword`, for every queue or some. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const modules = useAsyncData(() => knowledgeApi.textModules(tenantId.value))
const queues = useAsyncData(() => accessApi.queues(tenantId.value))

const editing = ref<TextModule | null>(null)
const dialogOpen = ref(false)
const form = ref({ name: '', keyword: '', body: '', queue_ids: [] as string[] })
const error = ref<string | null>(null)
const deleting = ref<TextModule | null>(null)
const deleteOpen = ref(false)

function openDialog(module: TextModule | null): void {
  editing.value = module
  form.value = {
    name: module?.name ?? '',
    keyword: module?.keyword ?? '',
    body: module?.body ?? '',
    queue_ids: [...(module?.queue_ids ?? [])],
  }
  error.value = null
  dialogOpen.value = true
}

watch(
  () => form.value.name,
  (name, before) => {
    const guess = (value: string) =>
      value
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 30)
    if (!editing.value && (!form.value.keyword || form.value.keyword === guess(before ?? ''))) {
      form.value.keyword = guess(name)
    }
  },
)

function toggleQueue(id: string, on: boolean): void {
  form.value.queue_ids = on ? [...form.value.queue_ids, id] : form.value.queue_ids.filter((each) => each !== id)
}

async function save(): Promise<void> {
  error.value = null
  try {
    const saved = editing.value
      ? await knowledgeApi.update(tenantId.value, editing.value.id, form.value)
      : await knowledgeApi.create(tenantId.value, form.value)
    notify.success(t('knowledge.saved', { keyword: saved.keyword }))
    dialogOpen.value = false
    await modules.reload()
  } catch (caught) {
    error.value = errorText(caught)
  }
}

function queueNames(module: TextModule): string {
  if (!module.queue_ids.length) {
    return t('knowledge.everyQueue')
  }
  return module.queue_ids.map((id) => queues.data.value?.find((queue) => queue.id === id)?.name ?? '?').join(', ')
}

function askDelete(module: TextModule): void {
  deleting.value = module
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const module = deleting.value!
  await knowledgeApi.remove(tenantId.value, module.id)
  notify.success(t('knowledge.deleted', { keyword: module.keyword }))
  await modules.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('knowledge.title')" :description="$t('knowledge.description')">
      <Button v-if="tenants.can('knowledge.manage')" data-test="create-module" @click="openDialog(null)"
        ><Plus class="size-4" /> {{ $t('knowledge.create') }}</Button
      >
    </PageHeader>
    <ErrorAlert v-if="modules.error.value" :message="modules.error.value" />
    <EmptyState
      v-else-if="modules.data.value?.length === 0"
      :title="$t('knowledge.empty')"
      :description="$t('knowledge.emptyHint')"
    >
      <template #icon><BookText class="size-8 text-muted-foreground" /></template>
    </EmptyState>
    <Card v-else-if="modules.data.value">
      <CardContent class="grid gap-2 pt-6">
        <div
          v-for="module in modules.data.value"
          :key="module.id"
          class="flex items-start gap-3 rounded-md border p-3"
          :data-test="`module-${module.keyword}`"
        >
          <code class="rounded bg-muted px-1.5 py-0.5 text-xs">::{{ module.keyword }}</code>
          <div class="min-w-0 flex-1">
            <p class="font-medium">{{ module.name }}</p>
            <p class="line-clamp-2 text-xs whitespace-pre-wrap text-muted-foreground">{{ module.body }}</p>
            <p class="mt-1 text-xs text-muted-foreground">{{ queueNames(module) }}</p>
          </div>
          <template v-if="tenants.can('knowledge.manage')">
            <Button
              variant="ghost"
              size="icon"
              :aria-label="$t('common.edit')"
              :data-test="`edit-module-${module.keyword}`"
              @click="openDialog(module)"
              ><Pencil class="size-4"
            /></Button>
            <Button
              variant="ghost"
              size="icon"
              :aria-label="$t('common.delete')"
              :data-test="`delete-module-${module.keyword}`"
              @click="askDelete(module)"
              ><Trash2 class="size-4"
            /></Button>
          </template>
        </div>
      </CardContent>
    </Card>

    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{{ editing ? $t('knowledge.edit') : $t('knowledge.create') }}</DialogTitle>
          <DialogDescription>{{ $t('knowledge.dialogText') }}</DialogDescription>
        </DialogHeader>
        <form class="grid gap-4" @submit.prevent="save">
          <ErrorAlert v-if="error" :message="error" />
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="grid gap-2">
              <Label for="module-name">{{ $t('knowledge.name') }}</Label>
              <Input id="module-name" v-model="form.name" maxlength="80" required autofocus />
            </div>
            <div class="grid gap-2">
              <Label for="module-keyword">{{ $t('knowledge.keyword') }}</Label>
              <Input id="module-keyword" v-model="form.keyword" maxlength="30" required />
            </div>
          </div>
          <div class="grid gap-2">
            <Label for="module-body">{{ $t('knowledge.text') }}</Label>
            <Textarea id="module-body" v-model="form.body" rows="7" required />
            <p class="text-xs text-muted-foreground">{{ $t('knowledge.placeholders') }}</p>
          </div>
          <div class="grid gap-2">
            <Label>{{ $t('knowledge.queues') }}</Label>
            <div class="flex flex-wrap gap-3 text-sm">
              <label
                v-for="queue in queues.data.value ?? []"
                :key="queue.id"
                class="flex items-center gap-2"
                :data-test="`module-queue-${queue.id}`"
              >
                <Checkbox
                  :model-value="form.queue_ids.includes(queue.id)"
                  @update:model-value="(on) => toggleQueue(queue.id, on === true)"
                />
                {{ queue.name }}
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" data-test="save-module">{{ $t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('knowledge.deleteTitle', { keyword: deleting?.keyword })"
      :description="$t('knowledge.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
