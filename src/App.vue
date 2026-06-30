<script setup lang="ts">
import { computed } from 'vue'
import { RouterView } from 'vue-router'
import { useAuth } from '@clerk/vue'
import AuthLoadingShell from '@/components/AuthLoadingShell.vue'
import ConvexClerkProvider from '@/providers/ConvexClerkProvider.vue'
import { hasClerkPublishableKey } from '@/lib/clerkConfig'

const clerkEnabled = hasClerkPublishableKey()
const auth = clerkEnabled ? useAuth() : null

const showClerkLoading = computed(
  () => clerkEnabled && auth !== null && !auth.isLoaded.value,
)
</script>

<template>
  <AuthLoadingShell v-if="showClerkLoading" label="Loading session…" />
  <ConvexClerkProvider v-else>
    <RouterView />
  </ConvexClerkProvider>
</template>
