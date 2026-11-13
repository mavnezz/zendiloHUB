<script setup lang="ts">
import { BookOpen } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/core/ui/card'

/** What other systems do with a key, as curl commands for this organization; and where the full reference is. */
const props = defineProps<{ tenantId: string }>()

const { t } = useI18n()
const origin = window.location.origin
const base = computed(() => `${origin}/api/v1/tenants/${props.tenantId}`)
const KEY = '-H "Authorization: Bearer zhk_…"'

const examples = computed(() => [
  { key: 'members', command: `curl ${KEY} \\\n  ${base.value}/members` },
  { key: 'auditLog', command: `curl ${KEY} \\\n  "${base.value}/audit-log?limit=20"` },
])
const title = (key: string) => t(`apiKeys.examples.${key}`)
</script>

<template>
  <Card>
    <CardHeader class="flex flex-row items-start justify-between gap-4">
      <div class="grid gap-1.5">
        <CardTitle>{{ $t('apiKeys.examplesTitle') }}</CardTitle>
        <p class="text-sm text-muted-foreground">{{ $t('apiKeys.usage') }}</p>
      </div>
      <Button as-child variant="outline" size="sm">
        <a href="/api/reference" target="_blank" rel="noopener" data-test="reference">
          <BookOpen class="size-4" /> {{ $t('apiKeys.reference') }}
        </a>
      </Button>
    </CardHeader>
    <CardContent class="grid gap-4">
      <div v-for="example in examples" :key="example.key" class="grid gap-1" :data-test="`example-${example.key}`">
        <p class="text-sm font-medium">{{ title(example.key) }}</p>
        <pre class="overflow-auto rounded-md border bg-muted p-3 text-xs">{{ example.command }}</pre>
      </div>
    </CardContent>
  </Card>
</template>
