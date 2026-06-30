<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { SignUp } from '@clerk/vue'
import AppNav from '@/components/AppNav.vue'

const route = useRoute()

const signUpFallback =
  import.meta.env.VITE_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL ?? '/dashboard'
const signInUrl = import.meta.env.VITE_CLERK_SIGN_IN_URL ?? '/sign-in'

const redirectUrl = computed(() => {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/')) {
    return redirect
  }
  return signUpFallback
})
</script>

<template>
  <div class="page">
    <AppNav />
    <main class="main">
      <div class="card">
        <h1>Sign up</h1>
        <SignUp
          path="/sign-up"
          routing="path"
          :force-redirect-url="redirectUrl"
          :fallback-redirect-url="signUpFallback"
          :sign-in-url="signInUrl"
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
