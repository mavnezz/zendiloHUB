<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/core/components/PageHeader.vue'
import ApiExamplesCard from '../components/ApiExamplesCard.vue'
import ApiKeysCard from '../components/ApiKeysCard.vue'

/** The organization's API keys, and how other systems use them. */
const route = useRoute()
const tenantId = computed(() => String(route.params.tenantId))
</script>

<template>
  <div class="grid gap-6">
    <PageHeader :title="$t('nav.apiKeys')" :description="$t('apiKeys.hint')" />
    <ApiKeysCard :tenant-id="tenantId" />
    <ApiExamplesCard :tenant-id="tenantId" />
  </div>
</template>
