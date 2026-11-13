<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { useSession } from '@/modules/identity/session'
import { roleLabel } from '../roles'
import { tenancyApi, type InvitationPreview } from '../api'
import { rememberInvitation, takePendingInvitation, useTenants } from '../tenants'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSession()
const tenants = useTenants()

const token = typeof route.query.token === 'string' ? route.query.token : ''
const preview = ref<InvitationPreview | null>(null)
const error = ref<string | null>(token ? null : t('invitation.missing'))
const loading = ref(Boolean(token))
const busy = ref(false)

const here = computed(() => route.fullPath)
const otherAccount = computed(
  () => session.user.value !== null && preview.value !== null && session.user.value.email !== preview.value.email,
)

if (token) {
  void session
    .load()
    .catch(() => undefined)
    .then(() => tenancyApi.previewInvitation(token))
    .then((loaded) => {
      preview.value = loaded
      if (session.user.value) {
        takePendingInvitation()
      } else {
        rememberInvitation(token)
      }
    })
    .catch((caught: unknown) => {
      error.value = errorText(caught)
    })
    .finally(() => {
      loading.value = false
    })
}

async function accept(): Promise<void> {
  busy.value = true
  try {
    const tenant = await tenancyApi.acceptInvitation(token)
    tenants.put(tenant)
    notify.success(t('invitation.joined', { tenant: tenant.name }))
    await router.push({ name: 'overview', params: { tenantId: tenant.id } })
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}

async function switchAccount(): Promise<void> {
  await session.logout()
  await router.push({ name: 'login', query: { redirect: here.value } })
}
</script>

<template>
  <div class="flex justify-center px-4 py-12 sm:py-20">
    <Card class="w-full max-w-md">
      <CardHeader class="text-center">
        <CardTitle class="text-xl">{{ $t('invitation.title') }}</CardTitle>
        <CardDescription v-if="loading">{{ $t('invitation.loading') }}</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-4">
        <ErrorAlert v-if="error" :title="$t('invitation.invalidTitle')" :message="error" />
        <template v-else-if="preview">
          <p class="text-center" data-test="invitation-text">
            {{
              $t('invitation.text', {
                tenant: preview.tenant_name,
                role: roleLabel(preview.role, [], preview.role_name),
              })
            }}
          </p>
          <p class="text-center text-sm text-muted-foreground">
            {{ $t('invitation.forEmail', { email: preview.email }) }}
          </p>
          <template v-if="!session.user.value">
            <p class="text-center text-sm text-muted-foreground">{{ $t('invitation.loginFirst') }}</p>
            <div class="grid gap-2 sm:grid-cols-2">
              <Button as-child variant="outline">
                <RouterLink :to="{ name: 'login', query: { redirect: here } }" data-test="login">
                  {{ $t('nav.login') }}
                </RouterLink>
              </Button>
              <Button as-child>
                <RouterLink :to="{ name: 'register', query: { redirect: here } }" data-test="register">
                  {{ $t('nav.register') }}
                </RouterLink>
              </Button>
            </div>
          </template>
          <template v-else-if="otherAccount">
            <p class="text-center text-sm" data-test="other-account">
              {{ $t('invitation.otherAccount', { email: session.user.value.email }) }}
            </p>
            <Button variant="outline" data-test="switch-account" @click="switchAccount">{{ $t('nav.logout') }}</Button>
          </template>
          <Button v-else :disabled="busy" data-test="accept" @click="accept">
            {{ busy ? $t('invitation.busy') : $t('invitation.accept', { tenant: preview.tenant_name }) }}
          </Button>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
