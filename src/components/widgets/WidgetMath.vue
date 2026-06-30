<script setup lang="ts">
import MathDisplay from '@/components/MathDisplay.vue'
import WidgetShell from '@/components/widgets/WidgetShell.vue'

defineProps<{
  latex: string
}>()
</script>

<template>
  <WidgetShell type="math">
    <MathDisplay class="widget-math" :latex="latex" />
  </WidgetShell>
</template>
