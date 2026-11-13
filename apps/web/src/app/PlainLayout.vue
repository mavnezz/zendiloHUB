<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import LocaleSwitcher from '@/core/components/LocaleSwitcher.vue'
import ThemeToggle from '@/core/components/ThemeToggle.vue'
import UserMenu from '@/modules/identity/components/UserMenu.vue'

const year = new Date().getFullYear()
const legal = ['imprint', 'privacy', 'terms'] as const
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
      <div class="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
        <RouterLink :to="{ name: 'start' }" class="flex items-center gap-2 font-semibold" data-test="brand">
          <img src="/favicon.svg" alt="" class="size-7" />
          <span>{{ $t('app.name') }}</span>
        </RouterLink>
        <div class="ml-auto flex items-center gap-1">
          <LocaleSwitcher />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>

    <main class="flex-1">
      <RouterView />
    </main>

    <footer class="border-t">
      <div
        class="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 text-sm text-muted-foreground"
      >
        <span>{{ $t('footer.copyright', { year }) }}</span>
        <nav class="flex flex-wrap gap-x-4 gap-y-2">
          <RouterLink v-for="page in legal" :key="page" :to="{ name: page }" class="hover:text-foreground">
            {{ $t(`footer.${page}`) }}
          </RouterLink>
        </nav>
      </div>
    </footer>
  </div>
</template>
