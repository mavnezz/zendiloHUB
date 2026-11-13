<script setup lang="ts">
import { Check, ChevronsUpDown, Plus } from '@lucide/vue'
import { useRouter } from 'vue-router'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/ui/dropdown-menu'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/core/ui/sidebar'
import { useTenants } from '../tenants'

const tenants = useTenants()
const router = useRouter()
const { isMobile } = useSidebar()

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

async function open(tenantId: string): Promise<void> {
  await router.push({ name: 'overview', params: { tenantId } })
}
</script>

<template>
  <SidebarMenu>
    <SidebarMenuItem>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <SidebarMenuButton
            size="lg"
            class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            data-test="tenant-switcher"
          >
            <div
              class="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sm font-semibold text-sidebar-primary-foreground"
            >
              {{ initials(tenants.current.value?.name ?? 'Z') }}
            </div>
            <div class="grid flex-1 text-left text-sm leading-tight">
              <span class="truncate font-semibold" data-test="tenant-name">{{ tenants.current.value?.name }}</span>
              <span v-if="tenants.current.value" class="truncate text-xs text-muted-foreground">
                {{ $t(`tenant.roles.${tenants.current.value.role}`) }}
              </span>
            </div>
            <ChevronsUpDown class="ml-auto" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          class="w-(--reka-dropdown-menu-trigger-width) min-w-56 rounded-lg"
          :side="isMobile ? 'bottom' : 'right'"
          align="start"
        >
          <DropdownMenuLabel class="text-xs text-muted-foreground">{{ $t('tenant.switch') }}</DropdownMenuLabel>
          <DropdownMenuItem
            v-for="tenant in tenants.tenants.value"
            :key="tenant.id"
            :disabled="tenant.status !== 'active'"
            :data-test="`tenant-${tenant.id}`"
            @select="open(tenant.id)"
          >
            <span class="truncate">{{ tenant.name }}</span>
            <span v-if="tenant.status !== 'active'" class="text-xs text-muted-foreground">
              ({{ $t('tenant.suspended') }})
            </span>
            <Check v-if="tenant.id === tenants.current.value?.id" class="ml-auto size-4" />
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem data-test="tenant-create" @select="router.push({ name: 'onboarding' })">
            <Plus class="size-4" /> {{ $t('tenant.create') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
</template>
