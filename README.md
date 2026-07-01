# Kyno

Vue 3 + Vite + Convex + Clerk app with RBAC and RLS-style authorization.

## Stack

- **Vue 3** + **Vite** + **TypeScript**
- **Clerk** — authentication
- **Convex** — backend, users table, permission middleware
- **convex-vue** — reactive queries/mutations

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Clerk

1. Create a Clerk application at [dashboard.clerk.com](https://dashboard.clerk.com).
2. Copy the **Publishable key** to `.env` as `VITE_CLERK_PUBLISHABLE_KEY`.
3. Create a **JWT template** named exactly `convex` (required).
4. Note the template **Issuer** URL for Convex.
5. In Clerk Dashboard → **Configure** → **Paths** → **Allowed redirect origins**, add `http://localhost:5173` (and your production URL when deploying).

### 3. Convex

```bash
npx convex dev
```

Set Convex environment variables:

```bash
npx convex env set CLERK_JWT_ISSUER_DOMAIN https://your-clerk-issuer.clerk.accounts.dev
npx convex env set SUPER_ADMIN_CLERK_ID user_your_clerk_id
```

Copy `VITE_CONVEX_URL` from the Convex dashboard into `.env`.

### 4. Environment file

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

### 5. Run

**Production / cloud Convex:**

```bash
npm run dev      # Vite (terminal 1)
npx convex dev   # Convex cloud dev deployment (terminal 2)
```

**Local Docker stack (Vite + optional phi-gateway; Convex on host):**

See [`docs/local-dev-docker.md`](docs/local-dev-docker.md).

```bash
cp .env.example .env.local   # once, fill secrets
npm install
npx convex login   # once
./scripts/dev-up.sh   # detached stack
```

## Domain classifier bench and self-improve

The phi-gateway **small** profile runs compact jailbreak + domain + switch classifiers. Regression fixtures live in `data/domain/bench/`.

| Task | Doc |
|------|-----|
| Gateway setup, health, reload | [`docs/domain-gateway-runbook.md`](docs/domain-gateway-runbook.md) |
| Manual 5-cycle prompt tuning | [`docs/compact-prompt-tuning-flow.md`](docs/compact-prompt-tuning-flow.md) |
| **Automated Groq + bench loop** | [`docs/self-improve-bench.md`](docs/self-improve-bench.md) |

Before self-improve: gateway on `small` profile, `PHI_GATEWAY_API_KEY` + `GROQ_API_KEY` in `.env.local`, then `init` then `run` (see doc for full checklist).

## Bootstrap admin

The first user whose Clerk ID matches `SUPER_ADMIN_CLERK_ID` gets the `admin` role on sign-up. Other users default to `user`.

Admins can promote/demote users from `/admin`.

## Routes

| Route | Access |
|-------|--------|
| `/` | Public landing |
| `/sign-in` | Clerk sign-in |
| `/sign-up` | Clerk sign-up |
| `/dashboard` | Authenticated users |
| `/admin` | Admin role only |

## Auth architecture

### Convex middleware (`convex/auth/`)

- **`wrappers.ts`** — `authedQuery`, `authedMutation`, `adminQuery`, `adminMutation`
- **`guards.ts`** — JWT validation, user load, permission checks, owner doc assertions
- **`permissions.ts`** — role → permission map (`admin`, `user`)
- **`acl.ts`** — row-level access helpers

Protected functions must use wrappers — no raw `query`/`mutation` for auth-gated data (except `getOrCreateUser` and `getMyRole` for bootstrap/guards).

### Frontend bridge

- **`AppAuthProvider.vue`** — Clerk session load, Convex `setAuth`, `getOrCreateUser`, single loading shell
- **`lib/authSession.ts`** — shared `clerkLoaded`, `convexReady`, `userRole` for guards and composables
- **Router guards** — `requiresAuth`, `requiresAdmin` (Clerk session + cached role)

## Project structure

```
convex/
  auth/           # RBAC middleware
  users.ts        # User CRUD + role management
  schema.ts       # users + profiles tables
src/
  providers/      # AppAuthProvider (Clerk ↔ Convex)
  composables/    # useAppAuth, usePermissions, useConvexAuthReady
  router/         # Routes + guards
  views/          # Landing, Dashboard, Admin
```

## Clerk JWT template

Template name: **`convex`**

Must match `applicationID` in `convex/auth.config.ts`.
