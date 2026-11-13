<script setup lang="ts">
import { ChevronsUpDown, LogOut, Settings, ShieldCheck } from '@lucide/vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { notify } from '@/core/notify'
import { Avatar, AvatarFallback } from '@/core/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/ui/dropdown-menu'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/core/ui/sidebar'
import { useSession } from '../session'

const session = useSession()
const router = useRouter()
const { isMobile } = useSidebar()

const email = computed(() => session.user.value?.email ?? '')
const initials = computed(() => email.value.slice(0, 2).toUpperCase())

async function logout(): Promise<void> {
  try {
    await session.logout()
  } catch (caught) {
    notify.error(caught)
  }
  await router.push({ name: 'login' })
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
            :aria-label="$t('nav.userMenu')"
            data-test="user-menu"
          >
            <Avatar class="size-8 rounded-lg">
              <AvatarFallback class="rounded-lg text-xs">{{ initials }}</AvatarFallback>
            </Avatar>
            <span class="truncate text-sm">{{ email }}</span>
            <ChevronsUpDown class="ml-auto size-4" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          class="w-(--reka-dropdown-menu-trigger-width) min-w-56 rounded-lg"
          :side="isMobile ? 'bottom' : 'right'"
          align="end"
        >
          <DropdownMenuLabel class="truncate font-normal text-muted-foreground">{{ email }}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem data-test="menu-account" @select="router.push({ name: 'account' })">
            <Settings class="size-4" /> {{ $t('nav.account') }}
          </DropdownMenuItem>
          <DropdownMenuItem
            v-if="session.isAdmin.value"
            data-test="menu-admin"
            @select="router.push({ name: 'admin-tenants' })"
          >
            <ShieldCheck class="size-4" /> {{ $t('nav.admin') }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem data-test="menu-logout" @select="logout">
            <LogOut class="size-4" /> {{ $t('nav.logout') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
</template>
