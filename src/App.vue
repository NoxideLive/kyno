<script setup lang="ts">
import { RouterView } from 'vue-router'
import AppAuthProvider from '@/providers/AppAuthProvider.vue'
</script>

<template>
  <AppAuthProvider>
    <RouterView />
  </AppAuthProvider>
</template>
