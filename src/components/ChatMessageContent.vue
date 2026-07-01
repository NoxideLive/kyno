<script setup lang="ts">
import { computed } from 'vue'
import { parseWidgetContent } from '@/lib/widgets'
import RichText from '@/components/RichText.vue'
import WidgetConfirm from '@/components/widgets/WidgetConfirm.vue'
import WidgetNotation from '@/components/widgets/WidgetNotation.vue'
import WidgetQuestion from '@/components/widgets/WidgetQuestion.vue'
import WidgetResponse from '@/components/widgets/WidgetResponse.vue'

const props = defineProps<{
  content: string
  contentFormat?: 'widget' | 'text'
  selectedAnswer?: string | null
}>()

const emit = defineEmits<{
  selectAnswer: [answer: string]
}>()

const widget = computed(() => parseWidgetContent(props.content, props.contentFormat))
</script>

<template>
  <WidgetResponse
    v-if="widget?.type === 'response'"
    :content="widget.content"
  />

  <WidgetQuestion
    v-else-if="widget?.type === 'question'"
    :question="widget.question"
    :suggested-answers="widget.suggestedAnswers"
    :selected-answer="selectedAnswer"
    @select="emit('selectAnswer', $event)"
  />

  <WidgetConfirm
    v-else-if="widget?.type === 'confirm'"
    :question="widget.question"
    :suggested-answers="widget.suggestedAnswers"
    :content="widget.content"
    :selected-answer="selectedAnswer"
    @select="emit('selectAnswer', $event)"
  />

  <WidgetNotation
    v-else-if="widget?.type === 'notation'"
    :title="widget.title"
    :content="widget.content"
  />

  <RichText
    v-else
    class="message-content message-content--markdown"
    :content="content"
  />
</template>
