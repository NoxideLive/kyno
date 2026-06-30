<script setup lang="ts">
import { RouterLink } from 'vue-router'
import {
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
} from '@clerk/vue'
import { usePermissions } from '@/composables/usePermissions'
import { hasClerkPublishableKey } from '@/lib/clerkConfig'

const { isAppAdmin } = usePermissions()
const clerkEnabled = hasClerkPublishableKey()
</script>

<template>
  <header class="nav">
    <RouterLink to="/" class="brand">Kyno</RouterLink>
    <nav class="links">
      <RouterLink to="/">Home</RouterLink>
      <template v-if="clerkEnabled">
        <Show when="signed-in">
          <RouterLink to="/dashboard">Dashboard</RouterLink>
          <RouterLink to="/chat">Chat</RouterLink>
          <RouterLink v-if="isAppAdmin" to="/admin">Admin</RouterLink>
          <UserButton />
        </Show>
        <Show when="signed-out">
          <SignInButton mode="redirect">
            <button type="button" class="nav-btn">Sign in</button>
          </SignInButton>
          <SignUpButton mode="redirect">
            <button type="button" class="nav-btn nav-btn-primary">Sign up</button>
          </SignUpButton>
        </Show>
      </template>
      <template v-else>
        <RouterLink to="/sign-in">Sign in</RouterLink>
        <RouterLink to="/sign-up">Sign up</RouterLink>
      </template>
    </nav>
  </header>
</template>

<style scoped>
.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
}

.brand {
  font-weight: 700;
  font-size: 1.125rem;
  color: var(--text);
  text-decoration: none;
}

.links {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.links a {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.875rem;
}

.links a.router-link-active {
  color: var(--text);
  font-weight: 500;
}

.nav-btn {
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: transparent;
  color: var(--muted);
  font-size: 0.875rem;
  padding: 0.35rem 0.75rem;
  cursor: pointer;
}

.nav-btn-primary {
  border-color: var(--text);
  color: var(--text);
  font-weight: 500;
}
</style>
