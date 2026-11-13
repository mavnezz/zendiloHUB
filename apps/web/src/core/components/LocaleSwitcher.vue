<script setup lang="ts">
import { Languages } from '@lucide/vue'
import { isLocale, useLocale } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/core/ui/dropdown-menu'

const { locale, locales, setLocale } = useLocale()

function choose(value: unknown): void {
  if (isLocale(value)) {
    setLocale(value)
  }
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="sm" :aria-label="$t('locale.label')" data-test="locale">
        <Languages class="size-4" />
        <span class="uppercase">{{ locale }}</span>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuLabel>{{ $t('locale.label') }}</DropdownMenuLabel>
      <DropdownMenuRadioGroup :model-value="locale" @update:model-value="choose">
        <DropdownMenuRadioItem v-for="option in locales" :key="option" :value="option" :data-test="`locale-${option}`">
          {{ $t(`locale.${option}`) }}
        </DropdownMenuRadioItem>
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
