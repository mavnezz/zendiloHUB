<script setup lang="ts">
import { Check, Minus } from '@lucide/vue'
import { computed } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { cn } from '@/core/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/core/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/core/ui/table'
import { tenancyApi, type Permission } from '../api'
import { useTenants } from '../tenants'

const tenants = useTenants()
const own = computed(() => tenants.current.value?.role)
const { data, error } = useAsyncData(() => tenancyApi.roles())

/** Permissions grouped by their area (`calls.view_all` → calls), in the server's order. */
const groups = computed(() => {
  const grouped = new Map<string, Permission[]>()
  for (const permission of Object.keys(data.value?.permissions ?? {}) as Permission[]) {
    const area = permission.split('.')[0] as string
    grouped.set(area, [...(grouped.get(area) ?? []), permission])
  }
  return [...grouped.entries()]
})

function allowed(permission: Permission, role: string): boolean {
  return (data.value?.permissions[permission] ?? []).includes(role as never)
}
</script>

<template>
  <div class="mx-auto grid max-w-5xl gap-6">
    <PageHeader :title="$t('roles.title')" :description="$t('roles.description')" />
    <ErrorAlert v-if="error" :message="error" />
    <template v-else-if="data">
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          v-for="role in data.roles"
          :key="role"
          :class="cn(role === own && 'border-primary')"
          :data-test="`role-card-${role}`"
        >
          <CardHeader>
            <CardTitle class="text-base">{{ $t(`tenant.roles.${role}`) }}</CardTitle>
            <CardDescription>{{ $t(`tenant.roleDescriptions.${role}`) }}</CardDescription>
          </CardHeader>
        </Card>
      </div>
      <Card>
        <CardContent class="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{{ $t('roles.permission') }}</TableHead>
                <TableHead v-for="role in data.roles" :key="role" class="text-center">
                  {{ $t(`tenant.roles.${role}`) }}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <template v-for="[area, permissions] in groups" :key="area">
                <TableRow class="bg-muted/40 hover:bg-muted/40">
                  <TableCell :colspan="data.roles.length + 1" class="text-xs font-medium tracking-wide uppercase">
                    {{ $t(`roles.groups.${area}`) }}
                  </TableCell>
                </TableRow>
                <TableRow v-for="permission in permissions" :key="permission" :data-test="`permission-${permission}`">
                  <TableCell>{{ $t(`roles.permissions.${permission}`) }}</TableCell>
                  <TableCell v-for="role in data.roles" :key="role" class="text-center">
                    <Check v-if="allowed(permission, role)" class="mx-auto size-4 text-primary" data-test="allowed" />
                    <Minus v-else class="mx-auto size-4 text-muted-foreground/50" />
                  </TableCell>
                </TableRow>
              </template>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
