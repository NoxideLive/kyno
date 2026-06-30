<script setup lang="ts">
import type { ChatRole } from '@/composables/useGroqChat'
import RichText from '@/components/RichText.vue'
import { quoteRoleLabel } from '@/lib/messageQuote'

defineProps<{
  role: ChatRole
  snippet: string
  compact?: boolean
  align?: 'left' | 'right'
}>()
</script>

<template>
  <blockquote
    class="quote-preview"
    :class="{
      'quote-preview--compact': compact,
      'quote-preview--right': align === 'right',
    }"
  >
    <span class="quote-preview__label">{{ quoteRoleLabel(role) }}</span>
    <RichText class="quote-preview__snippet quote-preview__snippet--rich" :content="snippet" />
  </blockquote>
</template>

<style scoped>
.quote-preview {
  margin: 0 0 0.5rem;
  padding: 0.375rem 0.5rem;
  border-left: 3px solid color-mix(in srgb, currentColor 35%, transparent);
  border-radius: 0 0.25rem 0.25rem 0;
  background: color-mix(in srgb, currentColor 8%, transparent);
}

.quote-preview--compact {
  margin: 0;
}

.quote-preview--right {
  border-left: none;
  border-right: 3px solid color-mix(in srgb, currentColor 35%, transparent);
  border-radius: 0.25rem 0 0 0.25rem;
  text-align: right;
}

.quote-preview__label {
  display: block;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.75;
  line-height: 1.2;
}

.quote-preview__snippet--rich {
  margin: 0.125rem 0 0;
  font-size: 0.8125rem;
  line-height: 1.35;
  opacity: 0.9;
}

.quote-preview__snippet--rich :deep(p) {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-preview__snippet--rich :deep(.katex) {
  font-size: 0.8125rem;
}
</style>
