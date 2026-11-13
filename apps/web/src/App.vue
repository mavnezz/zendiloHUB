<script setup lang="ts">
import 'vue-sonner/style.css'
import { RouterView } from 'vue-router'
import { useTheme } from '@/core/composables/use-theme'
import { Toaster } from '@/core/ui/sonner'
import { TooltipProvider } from '@/core/ui/tooltip'

const { dark } = useTheme()
</script>

<template>
  <TooltipProvider :delay-duration="300">
    <RouterView />
  </TooltipProvider>
  <Toaster :theme="dark ? 'dark' : 'light'" rich-colors close-button />
</template>
