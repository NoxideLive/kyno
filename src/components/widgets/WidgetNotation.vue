<script setup lang="ts">
import NotationDisplay from '@/components/NotationDisplay.vue'
import WidgetShell from '@/components/widgets/WidgetShell.vue'

defineProps<{
  title?: string
  content: string
}>()
</script>

<template>
  <WidgetShell type="notation">
    <p v-if="title" class="widget-notation__title">{{ title }}</p>
    <NotationDisplay class="widget-notation" :content="content" />
  </WidgetShell>
</template>

<style scoped>
.widget-notation__title {
  margin: 0 0 0.375rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--muted);
  line-height: 1.3;
}
</style>
