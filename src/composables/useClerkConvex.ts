import { fetchConvexJwtFromClerk } from '@/lib/clerkConvexAuth'
import { useAuth, useUser } from '@clerk/vue'

/**
 * Clerk + Convex helpers. Call from `<script setup>` only.
 */
export function useClerkConvex() {
  const auth = useAuth()
  const user = useUser()

  async function ensureConvexAuthReady(): Promise<void> {
    if (!auth.isLoaded.value) {
      throw new Error('Authentication is still loading.')
    }
    if (!auth.isSignedIn.value) {
      throw new Error('You must be signed in.')
    }
    const token = await fetchConvexJwtFromClerk(auth.getToken)
    if (!token) {
      throw new Error(
        'No Convex JWT from Clerk. Add a JWT template named "convex" in Clerk Dashboard.',
      )
    }
  }

  /** Wait until Clerk can mint a Convex JWT (guest: true immediately). */
  async function waitForConvexTokenReady(): Promise<boolean> {
    if (!auth.isLoaded.value) return false
    if (!auth.isSignedIn.value) return true
    const token = await fetchConvexJwtFromClerk(auth.getToken)
    return token !== null
  }

  return {
    auth,
    user,
    ensureConvexAuthReady,
    waitForConvexTokenReady,
  }
}
