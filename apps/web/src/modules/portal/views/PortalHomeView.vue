<script setup lang="ts">
import { LogOut, MailCheck, Plus } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ApiRequestError } from '@/core/api/http'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { formatDateTime } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { Badge } from '@/core/ui/badge'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Textarea } from '@/core/ui/textarea'
import { portalApi, type PortalTicket, type Visitor } from '../api'

/** The customer portal: sign in with a link by e-mail, then see one's tickets and open new ones. */
const route = useRoute()
const router = useRouter()
const tenantId = computed(() => String(route.params.tenantId))
const visitor = ref<Visitor | null>(null)
const tickets = ref<PortalTicket[]>([])
const phase = ref<'loading' | 'login' | 'sent' | 'closed' | 'in'>('loading')
const error = ref<string | null>(null)
const email = ref('')
const writing = ref(false)
const subject = ref('')
const body = ref('')
const busy = ref(false)

async function load(): Promise<void> {
  try {
    visitor.value = await portalApi.me(tenantId.value)
    tickets.value = await portalApi.tickets(tenantId.value)
    phase.value = 'in'
  } catch (caught) {
    if (caught instanceof ApiRequestError && caught.code === 'portal_login_required') {
      phase.value = 'login'
    } else if (caught instanceof ApiRequestError && caught.code === 'portal_closed') {
      phase.value = 'closed'
    } else {
      error.value = errorText(caught)
      phase.value = 'login'
    }
  }
}
onMounted(load)

async function requestLink(): Promise<void> {
  error.value = null
  busy.value = true
  try {
    await portalApi.requestLink(tenantId.value, email.value.trim())
    phase.value = 'sent'
  } catch (caught) {
    if (caught instanceof ApiRequestError && caught.code === 'portal_closed') {
      phase.value = 'closed'
    } else {
      error.value = errorText(caught)
    }
  } finally {
    busy.value = false
  }
}

async function open(): Promise<void> {
  error.value = null
  busy.value = true
  try {
    const made = await portalApi.open(tenantId.value, subject.value, body.value)
    await router.push({ name: 'portalTicket', params: { tenantId: tenantId.value, ticketId: made.id } })
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}

async function logout(): Promise<void> {
  await portalApi.logout(tenantId.value).catch(() => undefined)
  visitor.value = null
  phase.value = 'login'
}

const stateVariant = (state: PortalTicket['state']) =>
  state === 'closed' ? 'secondary' : state === 'waiting' ? 'outline' : 'default'
</script>

<template>
  <div class="mx-auto grid max-w-3xl gap-6 p-4 md:p-8">
    <header class="flex flex-wrap items-center gap-3">
      <h1 class="text-3xl font-semibold tracking-tight">{{ $t('portal.title') }}</h1>
      <div v-if="phase === 'in' && visitor" class="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
        <span data-test="visitor"
          >{{ visitor.name }}<template v-if="visitor.company_name"> · {{ visitor.company_name }}</template></span
        >
        <Button variant="ghost" size="sm" data-test="portal-logout" @click="logout"
          ><LogOut class="size-4" /> {{ $t('portal.logout') }}</Button
        >
      </div>
    </header>

    <ErrorAlert v-if="error" :message="error" />

    <p v-if="phase === 'closed'" class="text-muted-foreground" data-test="portal-closed">{{ $t('portal.closed') }}</p>

    <Card v-else-if="phase === 'login'" class="max-w-md">
      <CardHeader>
        <CardTitle class="text-base">{{ $t('portal.signIn') }}</CardTitle>
        <CardDescription>{{ $t('portal.signInText') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="grid gap-3" @submit.prevent="requestLink">
          <Label for="portal-email">{{ $t('portal.email') }}</Label>
          <Input
            id="portal-email"
            v-model="email"
            type="email"
            required
            autocomplete="email"
            data-test="portal-email"
          />
          <Button type="submit" :disabled="busy || !email.trim()" data-test="portal-send-link">{{
            $t('portal.sendLink')
          }}</Button>
        </form>
      </CardContent>
    </Card>

    <p v-else-if="phase === 'sent'" class="flex items-center gap-2" data-test="portal-sent">
      <MailCheck class="size-5 text-muted-foreground" /> {{ $t('portal.linkSent') }}
    </p>

    <template v-else-if="phase === 'in'">
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-medium">
          {{ visitor?.company_tickets ? $t('portal.companyTickets') : $t('portal.myTickets') }}
        </h2>
        <Button class="ml-auto" size="sm" data-test="portal-new" @click="writing = !writing"
          ><Plus class="size-4" /> {{ $t('portal.newRequest') }}</Button
        >
      </div>
      <form v-if="writing" class="grid gap-3 rounded-lg border p-4" data-test="portal-new-form" @submit.prevent="open">
        <Label for="portal-subject">{{ $t('portal.subject') }}</Label>
        <Input id="portal-subject" v-model="subject" maxlength="250" required data-test="portal-subject" />
        <Label for="portal-body">{{ $t('portal.message') }}</Label>
        <Textarea id="portal-body" v-model="body" rows="6" required data-test="portal-body" />
        <Button
          type="submit"
          class="justify-self-end"
          :disabled="busy || !subject.trim() || !body.trim()"
          data-test="portal-submit"
          >{{ $t('portal.submit') }}</Button
        >
      </form>
      <p v-if="tickets.length === 0" class="text-muted-foreground" data-test="portal-empty">{{ $t('portal.empty') }}</p>
      <div v-else class="grid gap-2">
        <RouterLink
          v-for="each in tickets"
          :key="each.id"
          :to="{ name: 'portalTicket', params: { tenantId, ticketId: each.id } }"
          class="flex items-center gap-3 rounded-lg border p-3 hover:bg-muted"
          :data-test="`portal-ticket-${each.id}`"
        >
          <span class="text-sm text-muted-foreground tabular-nums">#{{ each.number }}</span>
          <span class="truncate font-medium">{{ each.subject }}</span>
          <span class="ml-auto shrink-0 text-xs text-muted-foreground">{{ formatDateTime(each.updated_at) }}</span>
          <Badge :variant="stateVariant(each.state)">{{ $t(`portal.states.${each.state}`) }}</Badge>
        </RouterLink>
      </div>
    </template>
  </div>
</template>
