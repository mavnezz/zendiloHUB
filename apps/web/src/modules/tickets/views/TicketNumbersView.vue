<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import NativeSelect from '@/core/components/NativeSelect.vue'
import PageHeader from '@/core/components/PageHeader.vue'
import { errorText } from '@/core/i18n/i18n'
import { notify } from '@/core/notify'
import { Button } from '@/core/ui/button'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { Switch } from '@/core/ui/switch'
import { useTenants } from '@/modules/tenancy/tenants'
import { ticketsApi, type TicketNumbering, type TicketNumberingView } from '../api'

/** How the organization numbers its tickets, with a preview of the next number as it stands in subjects. */
const { t } = useI18n()
const tenants = useTenants()
const tenantId = computed(() => tenants.current.value!.id)
const form = ref<Required<TicketNumbering>>({
  format: 'increment',
  start: 1001,
  date_digits: 4,
  checksum: false,
  prefix: '#',
})
const saved = ref<TicketNumberingView | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const digitOptions = [3, 4, 5, 6].map((digits) => ({ value: String(digits), label: String(digits) }))
const dateDigits = computed({
  get: () => String(form.value.date_digits),
  set: (value: string) => (form.value.date_digits = Number(value)),
})

/** Luhn's check digit, as the server appends it. */
function checkDigit(digits: string): number {
  let total = 0
  ;[...digits].reverse().forEach((char, index) => {
    let value = Number(char)
    if (index % 2 === 0) {
      value *= 2
      if (value > 9) value -= 9
    }
    total += value
  })
  return (10 - (total % 10)) % 10
}

/** The next number with the form's settings: the server's for what is saved, else worked out here. */
const preview = computed(() => {
  const current = form.value
  const server = saved.value
  const same =
    server &&
    server.format === current.format &&
    server.start === current.start &&
    server.date_digits === current.date_digits &&
    server.checksum === current.checksum
  let number: string
  if (same) {
    number = String(server.next_number)
  } else {
    let base: string
    if (current.format === 'date') {
      const today = new Date()
      const day = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, '0')}${String(today.getDate()).padStart(2, '0')}`
      base = `${day}${'1'.padStart(current.date_digits, '0')}`
    } else {
      base = String(current.start)
    }
    number = current.checksum ? `${base}${checkDigit(base)}` : base
  }
  return `[${current.prefix.trim() || '#'}${number}]`
})

function show(view: TicketNumberingView): void {
  saved.value = view
  form.value = {
    format: view.format ?? 'increment',
    start: view.start ?? 1001,
    date_digits: view.date_digits ?? 4,
    checksum: view.checksum ?? false,
    prefix: view.prefix ?? '#',
  }
}

onMounted(async () => {
  try {
    show(await ticketsApi.numbering(tenantId.value))
  } catch (caught) {
    error.value = errorText(caught)
  }
})

async function save(): Promise<void> {
  error.value = null
  busy.value = true
  try {
    show(await ticketsApi.saveNumbering(tenantId.value, { ...form.value, start: Number(form.value.start) }))
    notify.success(t('ticketNumbers.saved'))
  } catch (caught) {
    error.value = errorText(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto grid max-w-3xl gap-6">
    <PageHeader :title="$t('ticketNumbers.title')" :description="$t('ticketNumbers.description')" />
    <Card>
      <CardContent class="grid gap-4 pt-6">
        <ErrorAlert v-if="error" :message="error" />
        <form class="grid gap-5" @submit.prevent="save">
          <fieldset class="grid gap-2">
            <legend class="mb-1 text-sm font-medium">{{ $t('ticketNumbers.format') }}</legend>
            <label
              v-for="format in ['increment', 'date'] as const"
              :key="format"
              class="flex items-start gap-2 rounded-md border p-3 text-sm has-[:checked]:border-primary"
            >
              <input
                v-model="form.format"
                type="radio"
                name="format"
                :value="format"
                class="mt-0.5 accent-primary"
                :data-test="`format-${format}`"
              />
              <span>
                <span class="font-medium">{{ $t(`ticketNumbers.${format}`) }}</span>
                <span class="block text-xs text-muted-foreground">{{ $t(`ticketNumbers.${format}Hint`) }}</span>
              </span>
            </label>
          </fieldset>
          <div v-if="form.format === 'increment'" class="grid gap-1.5">
            <Label for="numbers-start">{{ $t('ticketNumbers.start') }}</Label>
            <Input
              id="numbers-start"
              v-model.number="form.start"
              type="number"
              min="1"
              class="max-w-48"
              data-test="start"
            />
            <p class="text-xs text-muted-foreground">{{ $t('ticketNumbers.startHint') }}</p>
          </div>
          <div v-else class="grid gap-1.5">
            <Label for="numbers-digits">{{ $t('ticketNumbers.dateDigits') }}</Label>
            <NativeSelect
              id="numbers-digits"
              v-model="dateDigits"
              :options="digitOptions"
              class="max-w-24"
              data-test="date-digits"
            />
          </div>
          <label class="flex items-start gap-2 text-sm">
            <Switch v-model="form.checksum" data-test="checksum" />
            <span>
              <span class="font-medium">{{ $t('ticketNumbers.checksum') }}</span>
              <span class="block text-xs text-muted-foreground">{{ $t('ticketNumbers.checksumHint') }}</span>
            </span>
          </label>
          <div class="grid gap-1.5">
            <Label for="numbers-prefix">{{ $t('ticketNumbers.prefix') }}</Label>
            <Input id="numbers-prefix" v-model="form.prefix" maxlength="16" class="max-w-48" data-test="prefix" />
            <p class="text-xs text-muted-foreground">{{ $t('ticketNumbers.prefixHint') }}</p>
          </div>
          <p class="rounded-md bg-muted px-3 py-2 text-sm">
            {{ $t('ticketNumbers.next') }}: <span class="font-mono font-medium" data-test="preview">{{ preview }}</span>
          </p>
          <Button type="submit" class="justify-self-start" :disabled="busy" data-test="numbers-save">{{
            $t('common.save')
          }}</Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
