<script setup lang="ts">
import type { ChatDebugEvent } from '@/lib/chatDebug'

defineProps<{
  events: ChatDebugEvent[]
  errorMessage?: string
}>()

function eventLabel(event: ChatDebugEvent): string {
  switch (event.type) {
    case 'send_start':
      return `Send · ${event.model} · ${event.mode} · ${event.messageCount} msgs`
    case 'attempt':
      return `Attempt ${event.attempt} · ${event.mode}`
    case 'validation_failure':
      return `Validation failed · attempt ${event.attempt} · ${event.stage}`
    case 'retry_correction':
      return `Retry correction · attempt ${event.attempt}`
    case 'groq_error':
      return `Groq error · attempt ${event.attempt}`
    case 'success':
      return `Success · attempt ${event.attempt} · ${event.mode} · ${event.widgetCount} widget(s)`
    case 'final_failure':
      return 'Final failure'
    default: {
      const _exhaustive: never = event
      return String(_exhaustive)
    }
  }
}

function eventDetail(event: ChatDebugEvent): string | null {
  switch (event.type) {
    case 'validation_failure':
      return [
        event.message,
        event.widgetIndex !== undefined ? `widget #${event.widgetIndex}` : null,
        event.rawSnippet ? `raw: ${event.rawSnippet}` : null,
      ]
        .filter(Boolean)
        .join('\n')
    case 'retry_correction':
      return event.correction
    case 'groq_error':
      return [
        event.groqMessage,
        event.failedGeneration ? `failed_generation: ${event.failedGeneration}` : null,
      ]
        .filter(Boolean)
        .join('\n')
    case 'success':
      return event.widgetTypes.length > 0 ? `types: ${event.widgetTypes.join(', ')}` : null
    case 'final_failure':
      return [event.message, event.rawSnippet ? `raw: ${event.rawSnippet}` : null]
        .filter(Boolean)
        .join('\n')
    default:
      return null
  }
}
</script>

<template>
  <details v-if="events.length > 0 || errorMessage" class="debug-panel" open>
    <summary class="debug-summary">Debug</summary>
    <div class="debug-body">
      <p v-if="errorMessage" class="debug-error">{{ errorMessage }}</p>
      <div v-for="(event, index) in events" :key="index" class="debug-event">
        <p class="debug-label">{{ eventLabel(event) }}</p>
        <pre v-if="eventDetail(event)" class="debug-detail">{{ eventDetail(event) }}</pre>
      </div>
    </div>
  </details>
</template>

<style scoped>
.debug-panel {
  margin-top: 0.375rem;
  border: 1px dashed var(--border);
  border-radius: 0.375rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.6875rem;
  line-height: 1.4;
  color: var(--muted);
  background: color-mix(in srgb, var(--bg) 92%, var(--muted));
}

.debug-summary {
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  font-weight: 600;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  user-select: none;
}

.debug-body {
  padding: 0 0.5rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.debug-error {
  margin: 0;
  color: #b91c1c;
}

.debug-event {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.debug-label {
  margin: 0;
  font-weight: 600;
  color: var(--text);
}

.debug-detail {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--muted);
}
</style>
