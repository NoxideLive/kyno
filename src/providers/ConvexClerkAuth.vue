<script setup lang="ts">
import { useAuth, useSession } from '@clerk/vue'
import { useConvexClient, useConvexMutation } from 'convex-vue'
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch, type Ref } from 'vue'
import { api } from '../../convex/_generated/api'
import AuthLoadingShell from '@/components/AuthLoadingShell.vue'
import { CONVEX_JWT_TEMPLATE, fetchConvexJwtFromClerk } from '@/lib/clerkConvexAuth'
import { convexAuthReadyKey } from '@/composables/useConvexAuthReady'

const { isLoaded, isSignedIn } = useAuth()
const { session } = useSession()
const client = useConvexClient()
const { mutate: getOrCreateUser } = useConvexMutation(api.users.getOrCreateUser)

/** True only after Convex `setAuth` onChange(true) — JWT handshake finished. */
const authHandshakeDone = ref(false)
/** True after getOrCreateUser succeeds for the current session. */
const userProvisioned = ref(false)

provide(convexAuthReadyKey, { authHandshakeDone, userProvisioned })

const showContent = computed(() => {
  if (!isLoaded.value) return false
  if (isSignedIn.value !== true) return true
  return authHandshakeDone.value && userProvisioned.value
})

const loadingLabel = computed(() => {
  if (!isLoaded.value) return 'Loading session…'
  return 'Connecting…'
})

function waitUntilClerkLoaded(isLoadedRef: Ref<boolean>, timeoutMs = 20_000): Promise<boolean> {
  if (isLoadedRef.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      stop()
      resolve(false)
    }, timeoutMs)
    const stop = watch(isLoadedRef, (loaded) => {
      if (loaded) {
        clearTimeout(timer)
        stop()
        resolve(true)
      }
    })
  })
}

let syncRunning = false
let syncQueued = false

async function syncUser(): Promise<void> {
  if (!isLoaded.value || !session.value) return

  const getToken = ref(session.value.getToken.bind(session.value))
  const jwt = await fetchConvexJwtFromClerk(getToken)
  if (!jwt) return

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await getOrCreateUser({})
      userProvisioned.value = true
      return
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      const authError =
        msg.includes('UNAUTHENTICATED') ||
        msg.includes('Sign in required') ||
        msg.includes('Not authenticated')
      if (authError && attempt < 2) {
        await fetchConvexJwtFromClerk(getToken, 3)
        await nextTick()
        continue
      }
      if (authError) {
        console.warn('[ConvexClerkAuth] getOrCreateUser:', msg)
        return
      }
      throw e
    }
  }
}

async function coalescedSync(): Promise<void> {
  if (syncRunning) {
    syncQueued = true
    return
  }
  syncRunning = true
  try {
    do {
      syncQueued = false
      await syncUser().catch(() => {})
    } while (syncQueued)
  } finally {
    syncRunning = false
  }
}

function installConvexAuth() {
  client.setAuth(
    async () => {
      const loadedOk = await waitUntilClerkLoaded(isLoaded)
      if (!loadedOk || !session.value) return null
      try {
        return await session.value.getToken({ template: CONVEX_JWT_TEMPLATE })
      } catch {
        return null
      }
    },
    (isAuthenticated) => {
      if (!isAuthenticated) {
        authHandshakeDone.value = false
        userProvisioned.value = false
        return
      }
      void nextTick(() => {
        authHandshakeDone.value = true
        void coalescedSync()
      })
    },
  )
}

onMounted(() => {
  installConvexAuth()
})

onUnmounted(() => {
  authHandshakeDone.value = false
  userProvisioned.value = false
  client.setAuth(async () => null)
})

watch(session, () => {
  if (!isLoaded.value || !session.value) return
  if (!authHandshakeDone.value) return
  void nextTick(() => void coalescedSync())
})
</script>

<template>
  <slot v-if="showContent" />
  <AuthLoadingShell v-else :label="loadingLabel" />
</template>
