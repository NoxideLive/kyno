<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { SignIn } from '@clerk/vue'
import AppNav from '@/components/AppNav.vue'

const route = useRoute()

const signInFallback =
  import.meta.env.VITE_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL ?? '/dashboard'
const signUpUrl = import.meta.env.VITE_CLERK_SIGN_UP_URL ?? '/sign-up'

const redirectUrl = computed(() => {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/')) {
    return redirect
  }
  return signInFallback
})
</script>

<template>
  <div class="page">
    <AppNav />
    <main class="main">
      <div class="card">
        <h1>Sign in</h1>
        <SignIn
          path="/sign-in"
          routing="path"
          :force-redirect-url="redirectUrl"
          :fallback-redirect-url="signInFallback"
          :sign-up-url="signUpUrl"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
}

.main {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1.5rem;
}

.card {
  width: 100%;
  max-width: 28rem;
  padding: 2rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
}

h1 {
  margin: 0 0 1.5rem;
  font-size: 1.5rem;
  text-align: center;
}
</style>
