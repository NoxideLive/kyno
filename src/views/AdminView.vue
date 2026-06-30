<script setup lang="ts">
import { ref } from 'vue'
import { useConvexMutation, useConvexQuery } from 'convex-vue'
import AppNav from '@/components/AppNav.vue'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'

const { data: users, isPending } = useConvexQuery(api.users.listUsers, {})
const { mutate: setRole, isPending: saving } = useConvexMutation(api.users.setRole)

const message = ref('')
const error = ref('')

async function changeRole(userId: Id<'users'>, role: 'admin' | 'user') {
  message.value = ''
  error.value = ''
  try {
    await setRole({ userId, role })
    message.value = 'Role updated.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Update failed.'
  }
}
</script>

<template>
  <div class="page">
    <AppNav />
    <main class="main">
      <h1>Admin</h1>
      <p class="lead">Manage user roles.</p>

      <p v-if="message" class="msg success">{{ message }}</p>
      <p v-if="error" class="msg error">{{ error }}</p>

      <div v-if="isPending" class="muted">Loading users…</div>

      <table v-else-if="users?.length" class="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u._id">
            <td>{{ u.name ?? '—' }}</td>
            <td>{{ u.email ?? '—' }}</td>
            <td>
              <span class="badge" :class="u.role">{{ u.role }}</span>
            </td>
            <td class="actions">
              <button
                type="button"
                class="btn"
                :disabled="saving || u.role === 'admin'"
                @click="changeRole(u._id, 'admin')"
              >
                Make admin
              </button>
              <button
                type="button"
                class="btn btn-muted"
                :disabled="saving || u.role === 'user'"
                @click="changeRole(u._id, 'user')"
              >
                Make user
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <p v-else class="muted">No users yet.</p>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
}

.main {
  max-width: 56rem;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

h1 {
  margin: 0 0 0.25rem;
  font-size: 1.75rem;
}

.lead {
  color: var(--muted);
  margin: 0 0 1.5rem;
  font-size: 0.875rem;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.table th,
.table td {
  padding: 0.625rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.table th {
  color: var(--muted);
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.badge.admin {
  background: var(--accent-muted);
  color: var(--accent);
}

.badge.user {
  background: var(--bg);
  color: var(--muted);
}

.actions {
  display: flex;
  gap: 0.5rem;
}

.btn {
  padding: 0.25rem 0.625rem;
  border-radius: 0.25rem;
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 0.75rem;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-muted {
  color: var(--muted);
}

.msg {
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  margin: 0 0 1rem;
}

.msg.success {
  background: #ecfdf5;
  color: #047857;
}

.msg.error {
  background: #fef2f2;
  color: #b91c1c;
}

.muted {
  color: var(--muted);
  font-size: 0.875rem;
}
</style>
