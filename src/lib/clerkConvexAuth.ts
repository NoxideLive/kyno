import type { Ref } from 'vue'

/** Must match Clerk JWT template name and convex/auth.config.ts applicationID. */
export const CONVEX_JWT_TEMPLATE = 'convex' as const

export type ConvexJwtGetToken = (opts?: {
  template?: string
  skipCache?: boolean
}) => Promise<string | null>

export type FetchConvexJwtOptions = {
  forceRefreshToken?: boolean
  /** Clerk Convex integration active (sessionClaims.aud === "convex"). */
  useConvexIntegration?: boolean
  maxAttempts?: number
}

export async function fetchConvexJwtFromClerk(
  getToken: Ref<ConvexJwtGetToken | undefined>,
  options: FetchConvexJwtOptions = {},
): Promise<string | null> {
  const maxAttempts = options.maxAttempts ?? 5
  const skipCache = options.forceRefreshToken ?? false
  if (!getToken.value) return null
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const token = options.useConvexIntegration
        ? await getToken.value({ skipCache: skipCache || attempt > 1 })
        : await getToken.value({
            template: CONVEX_JWT_TEMPLATE,
            skipCache: skipCache || attempt > 1,
          })
      if (token) return token
    } catch {
      // retry
    }
    if (attempt < maxAttempts) {
      await new Promise((r) => setTimeout(r, 80 * attempt))
    }
  }
  return null
}

/** True when Clerk Convex integration is active (use getToken without template). */
export function usesClerkConvexIntegration(sessionClaims: Ref<unknown>): boolean {
  const claims = sessionClaims.value as { aud?: unknown } | null | undefined
  return claims?.aud === 'convex'
}
