<script setup lang="ts">
import { computed } from 'vue'
import { renderMessageHtml } from '@/lib/messageContent'

const props = withDefaults(
  defineProps<{
    latex: string
    displayMode?: boolean
  }>(),
  {
    displayMode: true,
  },
)

const renderedHtml = computed(() =>
  renderMessageHtml(props.latex, 'latex-only', { displayMode: props.displayMode }),
)
</script>

<template>
  <div class="math-display" v-html="renderedHtml" />
</template>

<style scoped>
.math-display {
  overflow-x: auto;
  word-break: normal;
}

.math-display :deep(.katex-display) {
  margin: 0;
  overflow-x: auto;
  overflow-y: hidden;
  font-size: 1.5em;
}
</style>
