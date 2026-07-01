<script setup lang="ts">
import { computed } from 'vue'
import RichText from '@/components/RichText.vue'
import { renderMessageHtml } from '@/lib/messageContent'
import { looksLikeLatex } from '../../shared/looksLikeLatex'

const props = withDefaults(
  defineProps<{
    content: string
    displayMode?: boolean
  }>(),
  {
    displayMode: true,
  },
)

const isLatex = computed(() => looksLikeLatex(props.content))

const renderedHtml = computed(() =>
  isLatex.value
    ? renderMessageHtml(props.content, 'latex-only', { displayMode: props.displayMode })
    : '',
)
</script>

<template>
  <div
    v-if="isLatex"
    class="notation-display notation-display--latex"
    v-html="renderedHtml"
  />
  <RichText
    v-else
    class="notation-display notation-display--text"
    :content="content"
  />
</template>

<style scoped>
.notation-display--latex {
  overflow-x: auto;
  word-break: normal;
}

.notation-display--latex :deep(.katex-display) {
  margin: 0;
  overflow-x: auto;
  overflow-y: hidden;
  font-size: 1.5em;
}
</style>
