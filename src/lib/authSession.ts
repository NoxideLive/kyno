import { ref, watch } from 'vue'
import type { AppRole } from '@/lib/permissions'

/** Clerk session finished loading (useAuth().isLoaded). */
export const clerkLoaded = ref(false)

/** Clerk signed-in state once loaded (true | false | undefined while loading). */
export const clerkSignedIn = ref<boolean | undefined>(undefined)

/** Convex JWT handshake + user provisioning complete. */
export const convexReady = ref(false)

/** Last Convex connect / provision error (shown in loading shell). */
export const convexError = ref<string | null>(null)

/** Role from getOrCreateUser — used by admin route guard. */
export const userRole = ref<AppRole | null>(null)

export function resetConvexSession(): void {
  convexReady.value = false
  convexError.value = null
  userRole.value = null
}

export function waitForClerkLoaded(timeoutMs = 30_000): Promise<boolean> {
  if (clerkLoaded.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      stop()
      resolve(clerkLoaded.value)
    }, timeoutMs)
    const stop = watch(clerkLoaded, (loaded) => {
      if (loaded) {
        window.clearTimeout(timer)
        stop()
        resolve(true)
      }
    })
  })
}

export function waitForConvexReady(timeoutMs = 30_000): Promise<boolean> {
  if (convexReady.value) return Promise.resolve(true)
  if (clerkSignedIn.value !== true) return Promise.resolve(false)
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      stop()
      resolve(convexReady.value)
    }, timeoutMs)
    const stop = watch(convexReady, (ready) => {
      if (ready) {
        window.clearTimeout(timer)
        stop()
        resolve(true)
      }
    })
  })
}
