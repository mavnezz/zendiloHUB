<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { identityApi } from '../api'
import AuthCard from '../components/AuthCard.vue'
import { useSession } from '../session'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSession()
const failed = ref<string | null>(null)

onMounted(async () => {
  const token = route.query.token
  if (typeof token !== 'string' || token === '') {
    failed.value = t('verify.missing')
    return
  }
  try {
    session.start((await identityApi.confirm(token)).user)
    notify.success(t('verify.done'))
    await router.replace({ name: 'start' })
  } catch {
    failed.value = t('verify.failedText')
  }
})
</script>

<template>
  <AuthCard :title="failed ? $t('verify.failedTitle') : $t('verify.title')">
    <template v-if="failed">
      <ErrorAlert :title="$t('verify.failedTitle')" :message="failed" />
      <Button as-child>
        <RouterLink :to="{ name: 'login' }">{{ $t('nav.login') }}</RouterLink>
      </Button>
    </template>
    <p v-else class="text-center text-sm text-muted-foreground">{{ $t('common.loading') }}</p>
  </AuthCard>
</template>
