<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { portalApi } from '../api'

/** The link from the e-mail: signs the customer in and leads to their tickets. */
const route = useRoute()
const router = useRouter()
const tenantId = String(route.params.tenantId)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    await portalApi.verify(tenantId, String(route.query.token ?? ''))
    await router.replace({ name: 'portal', params: { tenantId } })
  } catch (caught) {
    error.value = errorText(caught)
  }
})
</script>

<template>
  <div class="mx-auto grid max-w-md gap-4 p-4 md:p-8">
    <template v-if="error">
      <ErrorAlert :message="error" />
      <RouterLink :to="{ name: 'portal', params: { tenantId } }" class="text-sm underline" data-test="portal-again">{{
        $t('portal.newLink')
      }}</RouterLink>
    </template>
    <p v-else class="text-muted-foreground">{{ $t('portal.signingIn') }}</p>
  </div>
</template>
