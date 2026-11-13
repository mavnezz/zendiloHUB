<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import LocaleSwitcher from '@/core/components/LocaleSwitcher.vue'
import ThemeToggle from '@/core/components/ThemeToggle.vue'
import { Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from '@/core/ui/breadcrumb'
import { Separator } from '@/core/ui/separator'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/core/ui/sidebar'
import AppSidebar from './AppSidebar.vue'
import { navGroupOf } from './navigation'

const route = useRoute()
const page = computed(() => String(route.name ?? ''))
const group = computed(() => navGroupOf(page.value))
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset>
      <header
        class="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 rounded-t-xl border-b bg-background/80 px-4 backdrop-blur"
      >
        <SidebarTrigger class="-ml-1" :aria-label="$t('nav.toggleSidebar')" />
        <Separator orientation="vertical" class="mr-2 data-[orientation=vertical]:h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            <template v-if="group">
              <BreadcrumbItem class="hidden text-xs tracking-wide uppercase md:block">
                {{ $t(`nav.groups.${group.key}`) }}
              </BreadcrumbItem>
              <BreadcrumbSeparator class="hidden md:block" />
            </template>
            <BreadcrumbItem>
              <BreadcrumbPage data-test="breadcrumb-page">{{ $t(`nav.${page}`) }}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div class="ml-auto flex items-center gap-1">
          <LocaleSwitcher />
          <ThemeToggle />
        </div>
      </header>
      <main class="flex-1 p-4 md:p-6">
        <RouterView :key="String($route.params.tenantId)" />
      </main>
    </SidebarInset>
  </SidebarProvider>
</template>
