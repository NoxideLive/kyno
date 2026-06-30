import { computed, inject, type ComputedRef, type InjectionKey, type Ref } from 'vue'

export type ConvexAuthReadyContext = {
  authHandshakeDone: Ref<boolean>
  userProvisioned: Ref<boolean>
}

export const convexAuthReadyKey: InjectionKey<ConvexAuthReadyContext> =
  Symbol('convex-auth-ready')

/**
 * True while the Convex auth bridge is still initializing.
 * Missing provider (mount in progress) counts as pending, not signed-out.
 */
export function useConvexAuthPending(): ComputedRef<boolean> {
  const ctx = inject(convexAuthReadyKey, null)
  return computed(() => {
    if (!ctx) return true
    return !ctx.authHandshakeDone.value || !ctx.userProvisioned.value
  })
}

/** True once Convex JWT handshake finished and user row is provisioned. */
export function useConvexAuthReady(): ComputedRef<boolean> {
  const pending = useConvexAuthPending()
  return computed(() => !pending.value)
}
