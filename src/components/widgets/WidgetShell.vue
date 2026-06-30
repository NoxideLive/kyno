<script setup lang="ts">
import {
  CalculatorIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/vue/24/outline'

defineProps<{
  type: 'response' | 'question' | 'confirm' | 'math'
}>()
</script>

<template>
  <div class="widget-shell" :class="`widget-shell--${type}`">
    <div class="widget-shell__header">
      <ChatBubbleLeftRightIcon
        v-if="type === 'response'"
        class="widget-shell__icon"
        aria-hidden="true"
      />
      <CalculatorIcon
        v-else-if="type === 'math'"
        class="widget-shell__icon"
        aria-hidden="true"
      />
      <CheckCircleIcon
        v-else-if="type === 'confirm'"
        class="widget-shell__icon"
        aria-hidden="true"
      />
      <QuestionMarkCircleIcon
        v-else
        class="widget-shell__icon"
        aria-hidden="true"
      />
      <span v-if="type === 'question'" class="widget-shell__label">Question</span>
      <span v-else-if="type === 'confirm'" class="widget-shell__label">Confirm</span>
      <span v-else-if="type === 'math'" class="widget-shell__label">Math</span>
    </div>
    <div class="widget-shell__body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.widget-shell {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.widget-shell__header {
  display: flex;
  align-items: center;
  gap: 0.3125rem;
  color: var(--muted);
  line-height: 1;
  user-select: none;
}

.widget-shell__icon {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.widget-shell__label {
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.widget-shell--response .widget-shell__header {
  opacity: 0.55;
}

.widget-shell--question .widget-shell__header {
  color: var(--accent);
}

.widget-shell--confirm .widget-shell__header {
  color: var(--accent);
}

.widget-shell--math .widget-shell__header {
  color: var(--accent);
}

.widget-shell__body {
  min-width: 0;
}
</style>
