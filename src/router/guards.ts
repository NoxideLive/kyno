import type { RouteLocationNormalized, Router } from 'vue-router'
import { useAuth, useSession } from '@clerk/vue'
import type { ComputedRef, Ref } from 'vue'
import { watch } from 'vue'
import { ConvexClient } from 'convex/browser'
import { api } from '../../convex/_generated/api'
import { hasClerkPublishableKey, routeHasClerkHandshake } from '@/lib/clerkConfig'
import { CONVEX_JWT_TEMPLATE } from '@/lib/clerkConvexAuth'

function routeRequiresAuth(to: RouteLocationNormalized): boolean {
  return to.matched.some((record) => record.meta.requiresAuth === true)
}

function routeRequiresAdmin(to: RouteLocationNormalized): boolean {
  return to.matched.some((record) => record.meta.requiresAdmin === true)
}

function signedInRedirectTarget(to: RouteLocationNormalized): string {
  const redirect = to.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/')) {
    return redirect
  }
  return import.meta.env.VITE_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL ?? '/dashboard'
}

type ClerkGuardRefs = {
  isSignedIn: ComputedRef<boolean | undefined>
  isLoaded: Ref<boolean>
  session: ReturnType<typeof useSession>['session']
}

let authGuardsInstalled = false

/**
 * Install router guards from main.ts via `app.runWithContext` (after `clerkPlugin`).
 * @clerk/vue composables require an active app context — do not call bare from main.ts.
 * See clerk-vue-patterns → vue-router-guards.md.
 */
export function installAuthGuards(router: Router): void {
  if (authGuardsInstalled) return
  authGuardsInstalled = true
  const clerkEnabled = hasClerkPublishableKey()
  let clerk: ClerkGuardRefs | undefined

  if (clerkEnabled) {
    const auth = useAuth()
    const { session } = useSession()
    clerk = { isSignedIn: auth.isSignedIn, isLoaded: auth.isLoaded, session }
  }

  function waitForClerkLoaded(timeoutMs = 30_000): Promise<boolean> {
    if (!clerk) return Promise.resolve(false)
    if (clerk.isLoaded.value) return Promise.resolve(true)
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        stop()
        resolve(false)
      }, timeoutMs)
      const stop = watch(clerk!.isLoaded, (loaded) => {
        if (loaded) {
          window.clearTimeout(timer)
          stop()
          resolve(true)
        }
      })
    })
  }

  async function queryRoleWithClerkAuth(): Promise<'admin' | 'user' | null> {
    const url = import.meta.env.VITE_CONVEX_URL
    if (!url || !clerk?.session.value) return null

    const client = new ConvexClient(url)
    client.setAuth(async () => {
      if (!clerk?.session.value) return null
      return clerk.session.value.getToken({ template: CONVEX_JWT_TEMPLATE })
    })

    try {
      return await client.query(api.users.getMyRole, {})
    } finally {
      client.close()
    }
  }

  router.beforeEach(async (to) => {
    // Let Clerk finish OAuth / satellite handshake before auth redirects run.
    if (routeHasClerkHandshake(to)) {
      return true
    }

    if (!clerkEnabled) {
      if (routeRequiresAuth(to) || routeRequiresAdmin(to)) {
        return { path: '/sign-in', query: { redirect: to.fullPath } }
      }
      return true
    }

    const loaded = await waitForClerkLoaded()

    if (to.path === '/sign-in' || to.path === '/sign-up') {
      // Never redirect signed-in users away until Clerk has finished loading.
      if (!loaded || !clerk!.isLoaded.value) return true
      if (clerk!.isSignedIn.value === true) {
        return signedInRedirectTarget(to)
      }
      return true
    }

    if (!routeRequiresAuth(to) && !routeRequiresAdmin(to)) {
      return true
    }

    // Clerk still initializing — App.vue shows loading; do not redirect to sign-in.
    if (!loaded || !clerk!.isLoaded.value) return true

    if (clerk!.isSignedIn.value === false) {
      return { path: '/sign-in', query: { redirect: to.fullPath } }
    }

    if (routeRequiresAdmin(to)) {
      const role = await queryRoleWithClerkAuth()
      if (role !== 'admin') {
        return { path: '/dashboard' }
      }
    }

    return true
  })
}
