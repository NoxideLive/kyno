import type { RouteLocationNormalized } from 'vue-router'

const CLERK_HANDSHAKE_QUERY_KEYS = [
  '__clerk_handshake',
  '__clerk_handshake_nonce',
] as const

/** True when Clerk frontend is configured (publishable key present). */
export function hasClerkPublishableKey(): boolean {
  return Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY?.trim())
}

/** Clerk OAuth / satellite handshake is in progress — do not redirect away. */
export function routeHasClerkHandshake(to: RouteLocationNormalized): boolean {
  return CLERK_HANDSHAKE_QUERY_KEYS.some(
    (key) => typeof to.query[key] === 'string' && to.query[key] !== '',
  )
}

export function clerkAllowedRedirectOrigins(): string[] {
  const origins = new Set<string>([
    'http://localhost:5173',
    'http://localhost:4173',
  ])
  const siteUrl = import.meta.env.VITE_SITE_URL?.trim().replace(/\/$/, '')
  if (siteUrl?.startsWith('http')) origins.add(siteUrl)
  return [...origins]
}

export function clerkPluginOptions() {
  const env = import.meta.env
  return {
    publishableKey: env.VITE_CLERK_PUBLISHABLE_KEY!,
    signInUrl: env.VITE_CLERK_SIGN_IN_URL ?? '/sign-in',
    signUpUrl: env.VITE_CLERK_SIGN_UP_URL ?? '/sign-up',
    signInFallbackRedirectUrl: env.VITE_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL ?? '/dashboard',
    signUpFallbackRedirectUrl: env.VITE_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL ?? '/dashboard',
    allowedRedirectOrigins: clerkAllowedRedirectOrigins(),
  }
}

/** Routes that use Clerk + Convex auth bridge. */
export function routeUsesClerkAuth(path: string): boolean {
  if (path === '/') return false
  return true
}
