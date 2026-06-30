<script setup lang="ts">
import { useConvexClient } from 'convex-vue'
import { onMounted, onUnmounted } from 'vue'

const client = useConvexClient()

onMounted(() => {
  client.setAuth(async () => null)
})

onUnmounted(() => {
  client.setAuth(async () => null)
})
</script>

<template>
  <slot />
</template>
