<script setup lang="ts">
import { CircleUser, LogOut, Settings, ShieldCheck } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/core/ui/dropdown-menu'
import { useSession } from '../session'

const session = useSession()
const router = useRouter()

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
  <DropdownMenu v-if="session.user.value">
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="icon" :aria-label="$t('nav.userMenu')" data-test="user-menu">
        <CircleUser class="size-5" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-56">
      <DropdownMenuLabel class="truncate font-normal text-muted-foreground">{{
        session.user.value.email
      }}</DropdownMenuLabel>
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
  <div v-else class="flex items-center gap-1">
    <Button variant="ghost" size="sm" as-child>
      <RouterLink :to="{ name: 'login' }" data-test="nav-login">{{ $t('nav.login') }}</RouterLink>
    </Button>
    <Button size="sm" as-child class="hidden sm:inline-flex">
      <RouterLink :to="{ name: 'register' }" data-test="nav-register">{{ $t('nav.register') }}</RouterLink>
    </Button>
  </div>
</template>
