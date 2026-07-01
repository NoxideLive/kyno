import type { AuthConfig } from 'convex/server'

// Clerk Dashboard: JWT template named "convex" (must match applicationID below).
// Set on deployment: npx convex env set CLERK_JWT_ISSUER_DOMAIN https://....clerk.accounts.dev
const clerkIssuerDomain = (
  process.env.CLERK_JWT_ISSUER_DOMAIN ?? process.env.CLERK_FRONTEND_API_URL
)?.trim()

if (!clerkIssuerDomain) {
  throw new Error(
    'CLERK_JWT_ISSUER_DOMAIN is not set. Run: npx convex env set CLERK_JWT_ISSUER_DOMAIN https://your-issuer.clerk.accounts.dev',
  )
}

export default {
  providers: [
    {
      domain: clerkIssuerDomain,
      applicationID: 'convex',
    },
  ],
} satisfies AuthConfig
