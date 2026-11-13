<script setup lang="ts">
import { Moon, Sun } from '@lucide/vue'
import { useTheme } from '@/core/composables/use-theme'
import { Button } from '@/core/ui/button'

const theme = useTheme()
</script>

<template>
  <Button
    variant="ghost"
    size="icon"
    :aria-label="$t('theme.toggle')"
    :title="$t('theme.toggle')"
    data-test="theme"
    @click="theme.toggle()"
  >
    <Sun v-if="theme.dark.value" class="size-4" />
    <Moon v-else class="size-4" />
  </Button>
</template>
