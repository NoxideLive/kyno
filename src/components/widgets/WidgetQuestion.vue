<script setup lang="ts">
import { computed, ref } from 'vue'
import RichText from '@/components/RichText.vue'
import WidgetShell from '@/components/widgets/WidgetShell.vue'

const props = defineProps<{
  question: string
  suggestedAnswers: string[]
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

function onPick(answer: string): void {
  if (isLocked.value) return
  pickedAnswer.value = answer
  emit('select', answer)
}
</script>

<template>
  <WidgetShell type="question">
    <RichText class="widget-question__text" :content="question" />
    <div v-if="answers.length > 0" class="widget-question__answers">
      <button
        v-for="answer in answers"
        :key="answer"
        type="button"
        class="widget-question__answer"
        :class="{
          'widget-question__answer--selected': activeSelection === answer,
        }"
        :disabled="isLocked"
        @click="onPick(answer)"
      >
        {{ answer }}
      </button>
    </div>
    <p v-else class="widget-question__hint">Type a reply</p>
  </WidgetShell>
</template>

<style scoped>
.widget-question__text {
  margin: 0 0 0.625rem;
}

.widget-question__answers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.widget-question__answer {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text);
  font-size: 0.8125rem;
  line-height: 1.2;
  padding: 0.375rem 0.75rem;
  cursor: pointer;
}

.widget-question__answer:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.widget-question__answer:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.widget-question__answer--selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, var(--surface));
  color: var(--accent);
}

.widget-question__answer:focus-visible {
  outline: 2px solid var(--accent-muted);
  outline-offset: 2px;
}

.widget-question__hint {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--muted);
}
</style>
