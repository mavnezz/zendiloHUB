<script setup lang="ts">
import { ref } from 'vue'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { errorText } from '@/core/i18n/i18n'
import { Button } from '@/core/ui/button'
import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { useSession } from '../session'

/** The second step of a two-factor login: the code of the app (or a recovery code) for the challenge. */
const props = defineProps<{ challenge: string }>()
const emit = defineEmits<{ done: []; back: [] }>()

const session = useSession()
const code = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await session.completeTwoFactor(props.challenge, code.value)
    emit('done')
  } catch (caught) {
    error.value = errorText(caught)
    code.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="grid gap-4" data-test="two-factor-form" @submit.prevent="submit">
    <ErrorAlert v-if="error" :title="$t('login.failed')" :message="error" />
    <p class="text-sm text-muted-foreground">{{ $t('login.codeDescription') }}</p>
    <div class="grid gap-2">
      <Label for="code">{{ $t('login.code') }}</Label>
      <Input
        id="code"
        v-model="code"
        autocomplete="one-time-code"
        inputmode="text"
        maxlength="32"
        required
        autofocus
        data-test="code"
      />
      <p class="text-xs text-muted-foreground">{{ $t('login.codeHint') }}</p>
    </div>
    <Button type="submit" :disabled="busy || !code.trim()" data-test="verify">
      {{ busy ? $t('login.verifying') : $t('login.verify') }}
    </Button>
    <Button type="button" variant="ghost" data-test="back" @click="emit('back')">{{ $t('login.back') }}</Button>
  </form>
</template>
