<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

/** The platform administration: one tab per module that has admin pages. */
const tabs = [
  { name: 'admin-tenants', label: 'admin.tenants' },
  { name: 'admin-users', label: 'admin.users' },
  { name: 'admin-audit', label: 'audit.title' },
] as const
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-10">
    <h1 class="mb-4 text-sm font-medium tracking-wide text-muted-foreground uppercase">{{ $t('admin.title') }}</h1>
    <nav class="mb-8 flex gap-1 border-b" data-test="admin-tabs">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.name"
        :to="{ name: tab.name }"
        class="-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
        active-class="!border-primary !text-foreground font-medium"
      >
        {{ $t(tab.label) }}
      </RouterLink>
    </nav>
    <RouterView />
  </div>
</template>
