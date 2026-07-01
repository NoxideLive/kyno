<template>
  <div class="auth-loading" role="status" aria-live="polite" aria-busy="true">
    <div class="auth-loading-inner">
      <span class="spinner" aria-hidden="true" />
      <p class="label" :class="{ error: Boolean(error) }">{{ label }}</p>
      <button v-if="error" type="button" class="retry" @click="emit('retry')">
        Retry
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    error?: string | null
  }>(),
  {
    label: 'Loading…',
    error: null,
  },
)

const emit = defineEmits<{
  retry: []
}>()
</script>

<style scoped>
.auth-loading {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}

.auth-loading-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.spinner {
  width: 1.5rem;
  height: 1.5rem;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.label {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
  text-align: center;
  max-width: 20rem;
}

.label.error {
  color: #b91c1c;
}

.retry {
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--surface);
  color: var(--text);
  font-size: 0.875rem;
  padding: 0.375rem 0.75rem;
  cursor: pointer;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
