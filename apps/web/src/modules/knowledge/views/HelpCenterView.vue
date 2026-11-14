<script setup lang="ts">
import { ArrowLeft, Search } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ErrorAlert from '@/core/components/ErrorAlert.vue'
import { useAsyncData } from '@/core/composables/use-async-data'
import { Card, CardContent } from '@/core/ui/card'
import { Input } from '@/core/ui/input'
import { knowledgeApi } from '../api'

/** The public help center of an organization: its public articles, for customers, without logging in. */
const route = useRoute()
const tenantId = computed(() => String(route.params.tenantId))
const articleId = computed(() => (route.params.articleId ? String(route.params.articleId) : null))
const search = ref('')
const library = useAsyncData(() => knowledgeApi.helpCenter(tenantId.value, { q: search.value.trim() || undefined }))
const article = useAsyncData(() =>
  articleId.value ? knowledgeApi.helpArticle(tenantId.value, articleId.value) : Promise.resolve(null),
)
watch(articleId, () => void article.reload())
</script>

<template>
  <div class="mx-auto grid max-w-3xl gap-6 p-4 md:p-8">
    <header class="grid gap-3">
      <h1 class="text-3xl font-semibold tracking-tight">{{ $t('articles.helpCenter') }}</h1>
      <form class="relative" @submit.prevent="library.reload()">
        <Search class="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
        <Input
          v-model="search"
          type="search"
          class="pl-8"
          :placeholder="$t('articles.helpSearch')"
          data-test="help-search"
        />
      </form>
    </header>
    <template v-if="articleId">
      <RouterLink
        :to="{ name: 'helpCenter', params: { tenantId } }"
        class="flex items-center gap-1 text-sm text-muted-foreground"
        ><ArrowLeft class="size-4" /> {{ $t('articles.allArticles') }}</RouterLink
      >
      <ErrorAlert v-if="article.error.value" :message="article.error.value" />
      <article v-else-if="article.data.value" class="grid gap-3" data-test="help-article">
        <h2 class="text-2xl font-semibold">{{ article.data.value.title }}</h2>
        <p class="whitespace-pre-wrap">{{ article.data.value.body }}</p>
      </article>
    </template>
    <template v-else>
      <ErrorAlert v-if="library.error.value" :message="library.error.value" />
      <p v-else-if="library.data.value?.articles.length === 0" class="text-muted-foreground">
        {{ $t('articles.helpEmpty') }}
      </p>
      <div v-else-if="library.data.value" class="grid gap-3">
        <Card v-for="each in library.data.value.articles" :key="each.id">
          <CardContent class="pt-6">
            <RouterLink
              :to="{ name: 'helpArticle', params: { tenantId, articleId: each.id } }"
              class="font-medium hover:underline"
              :data-test="`help-${each.id}`"
              >{{ each.title }}</RouterLink
            >
            <p class="line-clamp-2 text-sm text-muted-foreground">{{ each.body }}</p>
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>
