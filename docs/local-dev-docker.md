# Local dev with Docker (dev profile only)

Production uses **cloud Convex**. Local dev runs:

| Where | What |
|-------|------|
| **Host** | `npx convex dev --env-file .env.local` |
| **Docker** | Vite (`dev` profile) |
| **Docker** | phi-gateway (`dev-gpu` profile, GPU required) |

Convex is **not** in Docker — the browser and Clerk auth connect to `localhost:3210` on the host directly, which avoids container networking issues.

## Stack

| Service | Where | Port | Hot reload |
|---------|-------|------|------------|
| `convex` | Host | 3210, 3211 | Yes — watches `convex/` + `shared/` |
| `vite` | Docker | 5173 | Yes (HMR) |
| `phi-gateway` | Docker | 8090 | No — restart container after Python edits |

All services read **[`.env.local`](../.env.local)** (copy from [`.env.example`](../.env.example)).

## First-time setup

```bash
cp .env.example .env.local
# Edit .env.local: VITE_* URLs, Clerk, Groq, CLERK_JWT_ISSUER_DOMAIN, PHI_GATEWAY_API_KEY

npm install
npx convex login   # once
```

## Daily dev

**Detached (recommended):**

```bash
./scripts/dev-up.sh
# stop: ./scripts/dev-down.sh
```

**Foreground (two terminals):**

**Terminal 1 — Convex (host):**

```bash
npx convex dev --env-file .env.local
```

**Terminal 2 — Docker (vite + optional phi):**

```bash
./scripts/dev-init.sh
# or: docker compose --env-file .env.local --profile dev up --build -d
# GPU: docker compose --env-file .env.local --profile dev --profile dev-gpu up --build -d
```

- App: http://localhost:5173  
- Convex API: http://localhost:3210  
- Phi health: http://localhost:8090/health  
- Dashboard: https://dashboard.convex.dev (local deployment under your project)

## `.env.local` (shared)

```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_CONVEX_URL=http://localhost:3210
VITE_CONVEX_SITE_URL=http://localhost:3211

CLERK_JWT_ISSUER_DOMAIN=https://....clerk.accounts.dev  # required for auth
PHI_GATEWAY_API_KEY=your-secret
PHI_GATEWAY_PORT=8090

SUPER_ADMIN_CLERK_ID=user_...
GROQ_API_KEY=gsk_...
```

Set Convex function env manually (or use `npx convex env set`):

```bash
npx convex env set CLERK_JWT_ISSUER_DOMAIN "https://....clerk.accounts.dev" --env-file .env.local --deployment local
```

After changing secrets in `.env.local`, restart `npx convex dev` or re-run `npx convex env set`.

`PHI_GATEWAY_URL` for Convex actions defaults to `http://localhost:8090` (host → Docker-mapped phi port).

## What reloads without restart

| Change | Action |
|--------|--------|
| `src/**/*.vue`, CSS | Vite HMR (automatic) |
| `convex/**/*.ts`, `shared/**/*.ts` | Convex push (automatic, host dev) |
| `services/phi-gateway/**/*.py` | `docker compose --profile dev-gpu restart phi-gateway` |
| Secrets in `.env.local` | Restart `npx convex dev` or `npx convex env set ...` |

## Host scripts

```bash
export PHI_GATEWAY_URL=http://localhost:8090
export PHI_GATEWAY_API_KEY=...   # from .env.local
python3 scripts/run_domain_pipeline.py
```

Classifier bench and automated compact-prompt self-improve require the **`dev-gpu`** profile with `PHI_GATEWAY_PROFILE=small`. See [self-improve-bench.md](self-improve-bench.md) for the full pre-run checklist.

## Production

Do not deploy the `dev` profile. Use cloud `VITE_CONVEX_URL` and Convex cloud env vars.

See also: [`docs/domain-gateway-runbook.md`](domain-gateway-runbook.md)
