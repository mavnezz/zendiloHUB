<script setup lang="ts">
import { Plus, X } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Checkbox } from '@/core/ui/checkbox'
import { Input } from '@/core/ui/input'
import { useTenants } from '@/modules/tenancy/tenants'
import { ticketsApi, type ChecklistItem } from '../api'

/** The ticket's checklist: what still has to be done (ticking needs `edit`). */
const props = defineProps<{ ticketId: string; editable: boolean }>()

const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const items = ref<ChecklistItem[]>([])
const text = ref('')
const done = computed(() => items.value.filter((item) => item.done).length)

async function load(): Promise<void> {
  items.value = await ticketsApi.checklist(tenantId.value, props.ticketId).catch(() => [])
}
onMounted(load)

async function run(action: () => Promise<unknown>): Promise<void> {
  try {
    await action()
  } catch (caught) {
    notify.error(caught)
  }
  await load()
}

async function add(): Promise<void> {
  const value = text.value.trim()
  if (value) {
    text.value = ''
    await run(() => ticketsApi.addChecklistItem(tenantId.value, props.ticketId, value))
  }
}
</script>

<template>
  <section class="grid gap-2 rounded-lg border p-3 text-sm" data-test="checklist">
    <h3 class="flex items-center justify-between text-xs font-medium tracking-wide text-muted-foreground uppercase">
      {{ $t('tickets.checklist') }}
      <span v-if="items.length" data-test="checklist-progress">{{ done }}/{{ items.length }}</span>
    </h3>
    <label v-for="item in items" :key="item.id" class="group flex items-center gap-2" :data-test="`item-${item.id}`">
      <Checkbox
        :model-value="item.done"
        :disabled="!editable"
        @update:model-value="
          (on) => run(() => ticketsApi.changeChecklistItem(tenantId, ticketId, item.id, { done: on === true }))
        "
      />
      <span :class="['flex-1', item.done && 'text-muted-foreground line-through']">{{ item.text }}</span>
      <Button
        v-if="editable"
        type="button"
        variant="ghost"
        size="icon"
        class="size-6 opacity-0 group-hover:opacity-100 focus:opacity-100"
        :aria-label="$t('common.remove')"
        :data-test="`remove-item-${item.id}`"
        @click.prevent="run(() => ticketsApi.deleteChecklistItem(tenantId, ticketId, item.id))"
        ><X class="size-3.5"
      /></Button>
    </label>
    <form v-if="editable" class="flex gap-1" @submit.prevent="add">
      <Input v-model="text" maxlength="300" class="h-8" :placeholder="$t('tickets.addItem')" data-test="new-item" />
      <Button type="submit" variant="outline" size="icon" class="size-8" :aria-label="$t('tickets.addItem')"
        ><Plus class="size-4"
      /></Button>
    </form>
  </section>
</template>
