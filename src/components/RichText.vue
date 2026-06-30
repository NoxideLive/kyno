<script setup lang="ts">
import { computed, ref } from 'vue'
import { renderMessageHtml } from '@/lib/messageContent'
import { useMarkdownEnhancements } from '@/composables/useMarkdownEnhancements'

const props = defineProps<{
  content: string
}>()

const root = ref<HTMLElement | null>(null)

const renderedHtml = computed(() => renderMessageHtml(props.content, 'markdown'))

useMarkdownEnhancements(root, () => renderedHtml.value)
</script>

<template>
  <div ref="root" class="rich-text markdown-content" v-html="renderedHtml" />
</template>
