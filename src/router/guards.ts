import type { RouteLocationNormalized, Router } from 'vue-router'
import { hasClerkPublishableKey, routeHasClerkHandshake } from '@/lib/clerkConfig'
import {
  clerkSignedIn,
  userRole,
  waitForClerkLoaded,
  waitForConvexReady,
} from '@/lib/authSession'

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

let authGuardsInstalled = false

/**
 * Clerk session guards only. Convex auth runs in AppAuthProvider.
 * Install from main.ts via `app.runWithContext` after clerkPlugin.
 */
export function installAuthGuards(router: Router): void {
  if (authGuardsInstalled) return
  authGuardsInstalled = true

  const clerkEnabled = hasClerkPublishableKey()

  router.beforeEach(async (to) => {
    if (routeHasClerkHandshake(to)) {
      return true
    }

    if (!clerkEnabled) {
      if (routeRequiresAuth(to) || routeRequiresAdmin(to)) {
        return { path: '/sign-in', query: { redirect: to.fullPath } }
      }
      return true
    }

    await waitForClerkLoaded()

    if (to.path === '/sign-in' || to.path === '/sign-up') {
      if (clerkSignedIn.value === true) {
        return signedInRedirectTarget(to)
      }
      return true
    }

    if (!routeRequiresAuth(to) && !routeRequiresAdmin(to)) {
      return true
    }

    if (clerkSignedIn.value === false) {
      return { path: '/sign-in', query: { redirect: to.fullPath } }
    }

    if (routeRequiresAdmin(to)) {
      await waitForConvexReady()
      if (userRole.value !== 'admin') {
        return { path: '/dashboard' }
      }
    }

    return true
  })
}
