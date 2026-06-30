<script setup lang="ts">
import { computed } from 'vue'
import { useUser } from '@clerk/vue'
import AppNav from '@/components/AppNav.vue'
import { useConvexAuthReady } from '@/composables/useConvexAuthReady'
import { useOptionalConvexQuery } from '@/composables/useOptionalConvexQuery'
import { api } from '../../convex/_generated/api'

const { user } = useUser()
const convexReady = useConvexAuthReady()

const { data: profileData, isPending: profilePending, error: profileError } =
  useOptionalConvexQuery(api.users.getMyProfile, () =>
    convexReady.value ? {} : 'skip',
  )

const { data: whoami, isPending: whoamiPending, error: whoamiError } =
  useOptionalConvexQuery(api.auth.smoke.whoami, () =>
    convexReady.value ? {} : 'skip',
  )

const displayName = computed(() => {
  return profileData.value?.user?.name ?? user.value?.fullName ?? 'User'
})

const role = computed(() => profileData.value?.user?.role ?? '—')
</script>

<template>
  <div class="page">
    <AppNav />
    <main class="main">
      <h1>Dashboard</h1>

      <section class="card">
        <h2>Profile</h2>
        <dl v-if="profileData && !profileError">
          <dt>Name</dt>
          <dd>{{ displayName }}</dd>
          <dt>Email</dt>
          <dd>{{ profileData?.user?.email ?? user?.primaryEmailAddress?.emailAddress ?? '—' }}</dd>
          <dt>Role</dt>
          <dd><span class="badge">{{ role }}</span></dd>
        </dl>
        <p v-else-if="profileError" class="error">{{ profileError.message }}</p>
        <p v-else-if="!convexReady" class="muted">Connecting Clerk to Convex…</p>
        <p v-else-if="profilePending" class="muted">Loading profile…</p>
        <p v-else class="muted">No profile data</p>
      </section>

      <section class="card">
        <h2>Whoami (Convex)</h2>
        <pre v-if="whoami">{{ JSON.stringify(whoami, null, 2) }}</pre>
        <p v-else-if="whoamiError" class="error">{{ whoamiError.message }}</p>
        <p v-else-if="!convexReady" class="muted">Connecting Clerk to Convex…</p>
        <p v-else-if="whoamiPending" class="muted">Loading…</p>
        <p v-else class="muted">No data</p>
      </section>
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
  padding: 2rem 1.5rem;
}

h1 {
  margin: 0 0 1.5rem;
  font-size: 1.75rem;
}

.card {
  padding: 1.25rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
  margin-bottom: 1rem;
}

.card h2 {
  margin: 0 0 1rem;
  font-size: 1rem;
}

dl {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: 0.5rem 1rem;
  margin: 0;
}

dt {
  color: var(--muted);
  font-size: 0.875rem;
}

dd {
  margin: 0;
  font-size: 0.875rem;
}

.badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  background: var(--accent-muted);
  color: var(--accent);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

pre {
  margin: 0;
  padding: 0.75rem;
  background: var(--bg);
  border-radius: 0.375rem;
  font-size: 0.75rem;
  overflow-x: auto;
}

.muted {
  color: var(--muted);
  font-size: 0.875rem;
  margin: 0;
}

.error {
  color: #b91c1c;
  font-size: 0.875rem;
  margin: 0;
}
</style>
