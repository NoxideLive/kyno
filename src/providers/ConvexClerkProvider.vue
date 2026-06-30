<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { hasClerkPublishableKey, routeUsesClerkAuth } from '@/lib/clerkConfig'
import ConvexClerkAuth from '@/providers/ConvexClerkAuth.vue'
import ConvexPublicAuth from '@/providers/ConvexPublicAuth.vue'

const route = useRoute()

const useClerkAuth = computed(
  () => hasClerkPublishableKey() && routeUsesClerkAuth(route.path),
)
</script>

<template>
  <ConvexClerkAuth v-if="useClerkAuth">
    <slot />
  </ConvexClerkAuth>
  <ConvexPublicAuth v-else>
    <slot />
  </ConvexPublicAuth>
</template>
