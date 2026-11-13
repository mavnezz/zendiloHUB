<script setup lang="ts">
import PageHeader from '@/core/components/PageHeader.vue'
import DeleteAccountCard from '@/modules/identity/components/DeleteAccountCard.vue'
import PasswordCard from '@/modules/identity/components/PasswordCard.vue'
import ProfileCard from '@/modules/identity/components/ProfileCard.vue'
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-10">
    <PageHeader :title="$t('account.title')" :description="$t('account.description')" />
    <div class="grid gap-6">
      <ProfileCard />
      <PasswordCard />
      <DeleteAccountCard />
    </div>
  </div>
</template>
