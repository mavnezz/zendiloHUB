<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/core/ui/sidebar'
import NavUser from '@/modules/identity/components/NavUser.vue'
import TenantSwitcher from '@/modules/tenancy/components/TenantSwitcher.vue'
import { useTenants } from '@/modules/tenancy/tenants'
import { navigation, navItemOf } from './navigation'

const route = useRoute()
const tenants = useTenants()
const active = computed(() => navItemOf(String(route.name ?? '')))

/** Only what the role may see; groups without visible entries disappear. */
const groups = computed(() =>
  navigation
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !item.permission || tenants.can(item.permission)),
    }))
    .filter((group) => group.items.length > 0),
)
</script>

<template>
  <Sidebar variant="inset" collapsible="icon">
    <SidebarHeader>
      <TenantSwitcher />
    </SidebarHeader>
    <SidebarContent v-if="tenants.current.value">
      <SidebarGroup v-for="group in groups" :key="group.key" :data-test="`nav-group-${group.key}`">
        <SidebarGroupLabel>{{ $t(`nav.groups.${group.key}`) }}</SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem v-for="item in group.items" :key="item.name">
            <SidebarMenuButton as-child :is-active="active === item.name" :tooltip="$t(`nav.${item.name}`)">
              <RouterLink
                :to="{ name: item.name, params: { tenantId: tenants.current.value?.id } }"
                :data-test="`nav-${item.name}`"
              >
                <component :is="item.icon" />
                <span>{{ $t(`nav.${item.name}`) }}</span>
              </RouterLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
