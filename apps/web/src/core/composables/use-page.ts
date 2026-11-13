import { computed, ref } from 'vue'
import { useAsyncData } from '@/core/composables/use-async-data'
/** A page of a list the API serves with offset and limit. */
interface Page {
  total: number
}

export const PAGE_SIZE = 50

/** One page of a long list (audit log, call log) with previous/next. */
export function usePage<P extends Page>(load: (offset: number, limit: number) => Promise<P>) {
  const offset = ref(0)
  const page = useAsyncData(() => load(offset.value, PAGE_SIZE))
  const total = computed(() => (page.data.value as Page | null | undefined)?.total ?? 0)

  function move(delta: number): void {
    offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
    void page.reload()
  }

  return {
    ...page,
    offset,
    total,
    hasPrevious: computed(() => offset.value > 0),
    hasNext: computed(() => offset.value + PAGE_SIZE < total.value),
    move,
  }
}
