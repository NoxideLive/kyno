<script setup lang="ts">
import { computed, ref } from 'vue'
import RichText from '@/components/RichText.vue'
import WidgetShell from '@/components/widgets/WidgetShell.vue'

const props = defineProps<{
  question: string
  suggestedAnswers: string[]
  content?: string
  selectedAnswer?: string | null
}>()

const emit = defineEmits<{
  select: [answer: string]
}>()

const pickedAnswer = ref<string | null>(null)

const answers = computed(() =>
  props.suggestedAnswers.map((answer) => answer.trim()).filter((answer) => answer.length > 0),
)

const activeSelection = computed(() => pickedAnswer.value ?? props.selectedAnswer ?? null)

const isLocked = computed(() => activeSelection.value !== null)

const contextContent = computed(() => props.content?.trim() ?? '')

function onPick(answer: string): void {
  if (isLocked.value) return
  pickedAnswer.value = answer
  emit('select', answer)
}
</script>

<template>
  <WidgetShell type="confirm">
    <RichText
      v-if="contextContent"
      class="widget-confirm__context"
      :content="contextContent"
    />
    <RichText class="widget-confirm__text" :content="question" />
    <div class="widget-confirm__answers">
      <button
        v-for="answer in answers"
        :key="answer"
        type="button"
        class="widget-confirm__answer"
        :class="{
          'widget-confirm__answer--selected': activeSelection === answer,
        }"
        :disabled="isLocked"
        @click="onPick(answer)"
      >
        {{ answer }}
      </button>
    </div>
  </WidgetShell>
</template>

<style scoped>
.widget-confirm__context {
  margin: 0 0 0.625rem;
}

.widget-confirm__text {
  margin: 0 0 0.625rem;
  font-weight: 500;
}

.widget-confirm__answers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.widget-confirm__answer {
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--surface);
  color: var(--text);
  font-size: 0.8125rem;
  line-height: 1.2;
  padding: 0.4375rem 0.875rem;
  cursor: pointer;
}

.widget-confirm__answer:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.widget-confirm__answer:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.widget-confirm__answer--selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, var(--surface));
  color: var(--accent);
}

.widget-confirm__answer:focus-visible {
  outline: 2px solid var(--accent-muted);
  outline-offset: 2px;
}
</style>
