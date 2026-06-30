import type { AuthConfig } from 'convex/server'

// Clerk Dashboard: JWT template named "convex" (must match applicationID below).
// Convex env: CLERK_JWT_ISSUER_DOMAIN (preferred) or CLERK_FRONTEND_API_URL
const clerkIssuerDomain =
  process.env.CLERK_JWT_ISSUER_DOMAIN ?? process.env.CLERK_FRONTEND_API_URL

export default {
  providers: [
    {
      domain: clerkIssuerDomain!,
      applicationID: 'convex',
    },
  ],
} satisfies AuthConfig
