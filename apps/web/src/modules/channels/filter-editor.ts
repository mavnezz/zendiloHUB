import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { notify } from '@/core/notify'
import { channelsApi, type FilterRequest, type MailFilter } from './api'

/** Creating, editing, deleting and reordering mail filters, for the pages that list them. */
export function useFilterEditor(tenantId: Ref<string>, reload: () => Promise<unknown>) {
  const { t } = useI18n()
  const editing = ref<MailFilter | null>(null)
  const scope = ref<string | null>(null)
  const dialogOpen = ref(false)
  const deleting = ref<MailFilter | null>(null)
  const deleteOpen = ref(false)

  /** A filter to edit, or (null) a new one for this mailbox (null: for all mailboxes). */
  function open(found: MailFilter | null, accountId: string | null = null): void {
    editing.value = found
    scope.value = accountId
    dialogOpen.value = true
  }

  async function save(body: FilterRequest): Promise<void> {
    const saved = editing.value
      ? await channelsApi.updateFilter(tenantId.value, editing.value.id, body)
      : await channelsApi.createFilter(tenantId.value, body)
    notify.success(t('channels.filters.saved', { name: saved.name }))
    await reload()
  }

  async function reorder(ids: string[], accountId: string | null): Promise<void> {
    try {
      await channelsApi.reorderFilters(tenantId.value, ids, accountId)
      await reload()
    } catch (caught) {
      notify.error(caught)
    }
  }

  function askDelete(found: MailFilter): void {
    deleting.value = found
    deleteOpen.value = true
  }

  async function remove(): Promise<void> {
    const found = deleting.value!
    await channelsApi.deleteFilter(tenantId.value, found.id)
    notify.success(t('channels.filters.deleted', { name: found.name }))
    await reload()
  }

  return { editing, scope, dialogOpen, deleting, deleteOpen, open, save, reorder, askDelete, remove }
}
