import type { Ref } from 'vue'

/** Must match Clerk JWT template name and convex/auth.config.ts applicationID. */
export const CONVEX_JWT_TEMPLATE = 'convex' as const

export type ConvexJwtGetToken = (opts: {
  template: string
  skipCache?: boolean
}) => Promise<string | null>

export async function fetchConvexJwtFromClerk(
  getToken: Ref<ConvexJwtGetToken | undefined>,
  maxAttempts = 5,
): Promise<string | null> {
  if (!getToken.value) return null
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const token = await getToken.value({
        template: CONVEX_JWT_TEMPLATE,
        skipCache: attempt > 1,
      })
      if (token) return token
    } catch {
      /* session / template not ready */
    }
    if (attempt < maxAttempts) {
      await new Promise((r) => setTimeout(r, 80 * attempt))
    }
  }
  return null
}
