<script setup lang="ts">
import RichText from '@/components/RichText.vue'
import WidgetShell from '@/components/widgets/WidgetShell.vue'

defineProps<{
  content: string
}>()
</script>

<template>
  <WidgetShell type="response">
    <RichText class="widget-response" :content="content" />
  </WidgetShell>
</template>
