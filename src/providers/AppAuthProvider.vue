<script setup lang="ts">
import { useAuth } from '@clerk/vue'
import { useConvexClient, useConvexMutation } from 'convex-vue'
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '../../convex/_generated/api'
import AuthLoadingShell from '@/components/AuthLoadingShell.vue'
import {
  clerkLoaded,
  clerkSignedIn,
  convexError,
  convexReady,
  resetConvexSession,
  userRole,
} from '@/lib/authSession'
import {
  fetchConvexJwtFromClerk,
  usesClerkConvexIntegration,
} from '@/lib/clerkConvexAuth'
import { hasClerkPublishableKey } from '@/lib/clerkConfig'

const clerkEnabled = hasClerkPublishableKey()
const { isLoaded, isSignedIn, getToken, sessionClaims } = useAuth()
const client = useConvexClient()
const { mutate: getOrCreateUser } = useConvexMutation(api.users.getOrCreateUser)

const authHandshakeDone = ref(false)
const userProvisioned = ref(false)

watch(
  () => isLoaded.value,
  (loaded) => {
    clerkLoaded.value = loaded
  },
  { immediate: true },
)

watch(
  () => isSignedIn.value,
  (signedIn) => {
    clerkSignedIn.value = signedIn
  },
  { immediate: true },
)

watch(
  [authHandshakeDone, userProvisioned],
  ([handshake, provisioned]) => {
    convexReady.value = handshake && provisioned
  },
  { immediate: true },
)

const showContent = computed(() => {
  if (!clerkEnabled) return true
  if (!isLoaded.value) return false
  if (isSignedIn.value !== true) return true
  return authHandshakeDone.value && userProvisioned.value
})

const loadingLabel = computed(() => {
  if (convexError.value) return convexError.value
  if (!isLoaded.value) return 'Loading session…'
  if (!authHandshakeDone.value) return 'Connecting…'
  if (!userProvisioned.value) return 'Setting up account…'
  return 'Loading…'
})

let setupGeneration = 0

async function provisionUser(): Promise<void> {
  userProvisioned.value = false
  try {
    const user = await getOrCreateUser({})
    userRole.value = user.role
    userProvisioned.value = true
    convexError.value = null
  } catch (e) {
    userProvisioned.value = false
    convexError.value = e instanceof Error ? e.message : String(e)
  }
}

function clearConvexAuthState(): void {
  authHandshakeDone.value = false
  userProvisioned.value = false
  resetConvexSession()
}

function installConvexAuth(): void {
  const generation = ++setupGeneration

  if (!isLoaded.value || isSignedIn.value !== true) {
    clearConvexAuthState()
    client.setAuth(async () => null)
    return
  }

  clearConvexAuthState()
  convexError.value = null

  client.setAuth(
    async ({ forceRefreshToken }) => {
      if (generation !== setupGeneration) return null
      if (!isLoaded.value || isSignedIn.value !== true) return null
      try {
        return await fetchConvexJwtFromClerk(getToken, {
          forceRefreshToken,
          useConvexIntegration: usesClerkConvexIntegration(sessionClaims),
        })
      } catch {
        return null
      }
    },
    (authenticated) => {
      if (generation !== setupGeneration) return
      if (!authenticated) {
        authHandshakeDone.value = false
        userProvisioned.value = false
        return
      }
      authHandshakeDone.value = true
      void provisionUser()
    },
  )
}

function retryConnect(): void {
  convexError.value = null
  installConvexAuth()
}

watch(
  () => [isLoaded.value, isSignedIn.value] as const,
  () => {
    installConvexAuth()
  },
  { immediate: true },
)

onUnmounted(() => {
  setupGeneration++
  clearConvexAuthState()
  client.setAuth(async () => null)
})
</script>

<template>
  <slot v-if="showContent" />
  <AuthLoadingShell
    v-else
    :label="loadingLabel"
    :error="convexError"
    @retry="retryConnect"
  />
</template>
