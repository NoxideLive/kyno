<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AppNav from '@/components/AppNav.vue'
</script>

<template>
  <div class="page">
    <AppNav />
    <main class="main">
      <h1>Kyno</h1>
      <p class="lead">Vue + Convex + Clerk with RBAC and row-level access.</p>
      <div class="actions">
        <RouterLink to="/sign-in" class="btn btn-primary">Sign in</RouterLink>
        <RouterLink to="/dashboard" class="btn">Dashboard</RouterLink>
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
}

.main {
  max-width: 40rem;
  margin: 0 auto;
  padding: 4rem 1.5rem;
  text-align: center;
}

h1 {
  font-size: 2.5rem;
  margin: 0 0 0.5rem;
}

.lead {
  color: var(--muted);
  margin: 0 0 2rem;
}

.actions {
  display: flex;
  gap: 0.75rem;
  justify-content: center;
}

.btn {
  display: inline-block;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  border: 1px solid var(--border);
  text-decoration: none;
  color: var(--text);
  font-size: 0.875rem;
}

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
</style>
