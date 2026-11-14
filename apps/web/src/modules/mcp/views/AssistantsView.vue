<script setup lang="ts">
import { Bot, Copy, Plus, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { formatDateTime } from '@/core/format'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { useTenants } from '@/modules/tenancy/tenants'
import { mcpApi } from '../api'

/** AI assistants (Claude, ChatGPT, …) the caller connects: they work with tickets with the caller's rights. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const connections = useAsyncData(() => mcpApi.list(tenantId.value))
const name = ref('Claude')
const token = ref<string | null>(null)
const error = ref<string | null>(null)
const endpoint = `${window.location.origin}/mcp`

const snippets = computed(() => {
  const secret = token.value ?? 'zhm_…'
  return {
    claudeCode: `claude mcp add --transport http zendilohub ${endpoint} --header "Authorization: Bearer ${secret}"`,
    json: JSON.stringify(
      { mcpServers: { zendilohub: { type: 'http', url: endpoint, headers: { Authorization: `Bearer ${secret}` } } } },
      null,
      2,
    ),
  }
})

async function connect(): Promise<void> {
  error.value = null
  try {
    const made = await mcpApi.connect(tenantId.value, name.value)
    token.value = made.token ?? null
    await connections.reload()
  } catch (caught) {
    error.value = errorText(caught)
  }
}

async function copy(text: string): Promise<void> {
  await navigator.clipboard?.writeText(text)
  notify.success(t('webhooks.copied'))
}

async function disconnect(id: string): Promise<void> {
  try {
    await mcpApi.disconnect(tenantId.value, id)
    notify.success(t('assistants.disconnected'))
  } catch (caught) {
    notify.error(caught)
  }
  await connections.reload()
}
</script>

<template>
  <div class="mx-auto grid max-w-4xl gap-6">
    <PageHeader :title="$t('assistants.title')" :description="$t('assistants.description')" />
    <Card>
      <CardHeader>
        <CardTitle class="text-base">{{ $t('assistants.connect') }}</CardTitle>
        <CardDescription>{{ $t('assistants.connectText') }}</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-3">
        <ErrorAlert v-if="error" :message="error" />
        <form class="flex gap-2" @submit.prevent="connect">
          <Input v-model="name" maxlength="80" :aria-label="$t('automation.name')" data-test="assistant-name" />
          <Button type="submit" :disabled="!name.trim()" data-test="connect"
            ><Plus class="size-4" /> {{ $t('assistants.create') }}</Button
          >
        </form>
        <div v-if="token" class="grid gap-3 rounded-md border border-primary p-3 text-sm" data-test="token">
          <p>{{ $t('assistants.tokenText') }}</p>
          <div v-for="(snippet, key) in snippets" :key="key" class="grid gap-1">
            <span class="text-xs font-medium">{{ $t(`assistants.snippets.${key}`) }}</span>
            <div class="flex items-start gap-2">
              <pre class="flex-1 overflow-x-auto rounded bg-muted p-2 text-xs">{{ snippet }}</pre>
              <Button
                variant="outline"
                size="icon"
                :aria-label="$t('webhooks.copy')"
                :data-test="`copy-${key}`"
                @click="copy(snippet)"
                ><Copy class="size-4"
              /></Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
    <Card>
      <CardHeader>
        <CardTitle class="text-base">{{ $t('assistants.connected') }}</CardTitle>
        <CardDescription>{{ $t('assistants.rules') }}</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-2">
        <p v-if="connections.data.value?.length === 0" class="text-sm text-muted-foreground">
          {{ $t('assistants.none') }}
        </p>
        <div
          v-for="connection in connections.data.value ?? []"
          :key="connection.id"
          class="flex items-center gap-3 rounded-md border p-3 text-sm"
          :data-test="`connection-${connection.name}`"
        >
          <Bot class="size-4 text-muted-foreground" />
          <div class="min-w-0 flex-1">
            <p class="font-medium">
              {{ connection.name }} <code class="text-xs text-muted-foreground">{{ connection.start }}…</code>
            </p>
            <p class="text-xs text-muted-foreground">
              {{
                connection.last_used_at
                  ? $t('assistants.lastUsed', { date: formatDateTime(connection.last_used_at) })
                  : $t('assistants.neverUsed')
              }}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="$t('assistants.disconnect')"
            :data-test="`disconnect-${connection.name}`"
            @click="disconnect(connection.id)"
            ><Trash2 class="size-4"
          /></Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
