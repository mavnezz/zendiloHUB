import { ref, shallowRef } from 'vue'
import { errorText } from '../i18n/i18n'

/** Loads data once (and again on reload), tracking loading and error state. */
export function useAsyncData<T>(loader: () => Promise<T>, { immediate = true } = {}) {
  const data = shallowRef<T | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function reload(): Promise<void> {
    loading.value = true
    try {
      data.value = await loader()
      error.value = null
    } catch (caught) {
      error.value = errorText(caught)
    } finally {
      loading.value = false
    }
  }

  if (immediate) {
    void reload()
  }
  return { data, error, loading, reload }
}
