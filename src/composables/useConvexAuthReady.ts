import { computed } from 'vue'
import { clerkSignedIn, convexReady } from '@/lib/authSession'

/** True while signed-in user is waiting for Convex auth + provisioning. */
export function useConvexAuthPending() {
  return computed(() => clerkSignedIn.value === true && !convexReady.value)
}

/** True once Convex is authenticated and the user row exists. */
export function useConvexAuthReady() {
  return computed(() => clerkSignedIn.value === true && convexReady.value)
}
