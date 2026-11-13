<script setup lang="ts">
import { Pencil, Plus, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmDialog from '@/core/components/ConfirmDialog.vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { useTenants } from '@/modules/tenancy/tenants'
import { channelsApi, type TemplateKind, type TextTemplate } from '../api'
import TemplateDialog from '../components/TemplateDialog.vue'

/** Signatures and salutations; each queue picks one of each (on the page "E-mail per queue"). */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const data = useAsyncData(() => channelsApi.templates(tenantId.value))
const KINDS: TemplateKind[] = ['salutation', 'signature']

const kind = ref<TemplateKind>('signature')
const editing = ref<TextTemplate | null>(null)
const dialogOpen = ref(false)
const deleting = ref<TextTemplate | null>(null)
const deleteOpen = ref(false)

function of(each: TemplateKind): TextTemplate[] {
  return (data.data.value?.templates ?? []).filter((template) => template.kind === each)
}

function openDialog(each: TemplateKind, template: TextTemplate | null): void {
  kind.value = each
  editing.value = template
  dialogOpen.value = true
}

async function save(body: { kind: TemplateKind; name: string; body: string }): Promise<void> {
  const template = editing.value
    ? await channelsApi.updateTemplate(tenantId.value, editing.value.id, body)
    : await channelsApi.createTemplate(tenantId.value, body)
  notify.success(t('channels.templates.saved', { name: template.name }))
  await data.reload()
}

function askDelete(template: TextTemplate): void {
  deleting.value = template
  deleteOpen.value = true
}

async function remove(): Promise<void> {
  const template = deleting.value!
  await channelsApi.deleteTemplate(tenantId.value, template.id)
  notify.success(t('channels.templates.deleted', { name: template.name }))
  await data.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('channels.templates.title')" :description="$t('channels.templates.description')" />
    <ErrorAlert v-if="data.error.value" :message="data.error.value" />
    <template v-else-if="data.data.value">
      <Card v-for="each in KINDS" :key="each" :data-test="`kind-${each}`">
        <CardHeader>
          <CardTitle class="flex items-center justify-between text-base">
            {{ $t(`channels.templates.kinds.${each}`) }}
            <Button size="sm" variant="outline" :data-test="`create-${each}`" @click="openDialog(each, null)">
              <Plus class="size-4" /> {{ $t(`channels.templates.create.${each}`) }}
            </Button>
          </CardTitle>
          <CardDescription>{{ $t(`channels.templates.hint.${each}`) }}</CardDescription>
        </CardHeader>
        <CardContent class="grid gap-3">
          <p v-if="of(each).length === 0" class="text-sm text-muted-foreground">{{ $t('channels.templates.none') }}</p>
          <div
            v-for="template in of(each)"
            :key="template.id"
            class="flex items-start justify-between gap-4 rounded-md border p-3"
            :data-test="`template-${template.name}`"
          >
            <div class="min-w-0">
              <p class="font-medium">{{ template.name }}</p>
              <pre class="mt-1 font-sans text-xs whitespace-pre-wrap text-muted-foreground">{{ template.body }}</pre>
            </div>
            <span class="flex shrink-0">
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.edit')"
                :data-test="`edit-${template.name}`"
                @click="openDialog(each, template)"
                ><Pencil class="size-4"
              /></Button>
              <Button
                variant="ghost"
                size="icon"
                :aria-label="$t('common.delete')"
                :data-test="`delete-${template.name}`"
                @click="askDelete(template)"
                ><Trash2 class="size-4"
              /></Button>
            </span>
          </div>
        </CardContent>
      </Card>
    </template>
    <TemplateDialog
      v-model:open="dialogOpen"
      :kind="kind"
      :initial="editing"
      :placeholders="data.data.value?.placeholders ?? []"
      :save="save"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      :title="$t('channels.templates.deleteTitle', { name: deleting?.name })"
      :description="$t('channels.templates.deleteText')"
      :confirm-label="$t('common.delete')"
      destructive
      :action="remove"
    />
  </div>
</template>
