# Self-improve bench

Automated multi-iteration compact prompt tuning for the **small** phi-gateway profile.

| Role | System |
|------|--------|
| **Propose** | Groq `openai/gpt-oss-20b` — diagnose failures, plan patches, edit compact rules/overlay, curate bench cases |
| **Evaluate** | Local phi-gateway (Qwen2.5-1.5B on `small` profile) — 600-case classifier bench |

Production files (`data/domain/bench/*.json`, `data/domain/compact_prompt_overlay.json`) are **never modified**. Each run stores immutable snapshots under `data/domain/bench/self-improve/runs/{run-id}/` (gitignored).

Manual operator loop (no Groq): [compact-prompt-tuning-flow.md](compact-prompt-tuning-flow.md).

Gateway setup and classify API: [domain-gateway-runbook.md](domain-gateway-runbook.md).

---

## Before you run

Complete this checklist once per machine/session.

### 1. Hardware and gateway profile

Self-improve **requires** the gateway on the **`small`** profile with compact prompts:

| Check | Command / value |
|-------|-----------------|
| GPU available | Docker `dev-gpu` profile or host phi-gateway with CUDA |
| Profile | `PHI_GATEWAY_PROFILE=small` |
| Prompt variant | `PHI_GATEWAY_PROMPT_VARIANT=compact` or `auto` (compact on small) |
| Models loaded | `/health` → `phi_loaded=true`, `profile=small` |

Bench reload uses gateway **test mode**: prompts are written to `compact_prompt_*_test.json`, reloaded via `POST /admin/reload-prompts`, then production mode is restored after each bench.

### 2. Start phi-gateway

**Docker (recommended):**

```bash
cp .env.example .env.local   # once — set PHI_GATEWAY_API_KEY, HF_TOKEN if needed
docker compose --env-file .env.local --profile dev-gpu up -d phi-gateway
```

Or use `./scripts/dev-up.sh` (see [local-dev-docker.md](local-dev-docker.md)).

First boot can take several minutes while HuggingFace models download into the cache.

### 3. Environment variables

Load from `.env.local` before running the CLI (the script also reads keys from that file):

```bash
export PHI_GATEWAY_URL=http://localhost:8090
set -a && source .env.local && set +a
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `PHI_GATEWAY_URL` | Yes | Gateway base URL (default `http://localhost:8090`) |
| `PHI_GATEWAY_API_KEY` | Yes | `POST /admin/reload-prompts` during bench (iter 0 and every iter) |
| `GROQ_API_KEY` | Yes for iter ≥ 1 | Groq propose phases; loaded from env, `.env.local`, or `npx convex env get GROQ_API_KEY` |
| `PHI_GATEWAY_PROFILE` | Yes (gateway) | Must be `small` for self-improve |
| `SELF_IMPROVE_GROQ_MODEL` | No | Default `openai/gpt-oss-20b` |
| `SELF_IMPROVE_GROQ_REASONING_EFFORT` | No | Default `medium` (`low` \| `medium` \| `high`) |
| `SELF_IMPROVE_MAX_METRIC_REGRESSION` | No | Accept gate: max key metric drop (default `0.08`) |
| `SELF_IMPROVE_MAX_PATTERN_REGRESSION` | No | Max non-target pattern increase (default `5`) |
| `SELF_IMPROVE_MAX_PASS_RATE_REGRESSION` | No | Max pass-rate drop (default `0.015`) |
| `SELF_IMPROVE_MIN_PASS_RATE_IMPROVEMENT` | No | Pass-rate gain for overall accept (default `0.015`) |

See [`.env.example`](../.env.example) for the full gateway block.

### 4. Production fixtures present

These must exist in the repo (committed):

```
data/domain/bench/bench.config.json
data/domain/bench/jailbreak.json
data/domain/bench/domain.json
data/domain/bench/switch.json
data/domain/compact_prompt_overlay.json
```

Cold-start `init` copies the prod bench into `iter-0/bench/` and starts from empty compact rules/overlay unless you `--seed-run`.

### 5. Preflight

```bash
# Gateway ready on small profile
curl -sf http://localhost:8090/health | jq '{profile, phi_loaded, roles}'

# Keys loaded (no output = OK)
python3 -c "
import os; from pathlib import Path
for k in ('PHI_GATEWAY_API_KEY',):
    assert os.environ.get(k), f'missing {k}'
print('PHI_GATEWAY_API_KEY ok')
"

# Optional: smoke the prod bench (~3 min)
PHI_GATEWAY_URL=http://localhost:8090 python3 scripts/run_classifier_bench.py
```

---

## How to run

CLI entry point: `scripts/run_self_improve_bench.py`

### `init` vs `run`

| Command | Creates new run? | What it does |
|---------|------------------|--------------|
| **`init`** | **Yes** | New run dir, `iter-0` baseline bench (~3 min), sets active run |
| **`run`** | **No** | Continues the **active** run (or `--run-id`) from `latest_iter + 1` |

`run` does **not** call `init`. To start fresh, always run `init` first (or `runs use` to switch to another existing run).

### End-to-end workflow

```bash
cd /path/to/kyno
export PHI_GATEWAY_URL=http://localhost:8090
set -a && source .env.local && set +a

# 1. Create run (baseline iter-0 only)
python3 scripts/run_self_improve_bench.py init --run-id caps-compact-v2

# 2. Improve loop — up to 5 iters, stops after 3 consecutive rejects
python3 scripts/run_self_improve_bench.py run --run-id caps-compact-v2

# 3. Inspect progress
python3 scripts/run_self_improve_bench.py status --run-id caps-compact-v2

# 4. Export best accepted iteration for manual prod promotion
python3 scripts/run_self_improve_bench.py finalize --run-id caps-compact-v2
```

**Fork** from a prior run’s last **accepted** snapshot (copies prompts, bench, integration history):

```bash
python3 scripts/run_self_improve_bench.py init --run-id fork-v2 --seed-run caps-compact-v2
python3 scripts/run_self_improve_bench.py run --run-id fork-v2
```

**Single iteration** (e.g. after inspecting `context`):

```bash
python3 scripts/run_self_improve_bench.py iteration --run-id caps-compact-v2 --number 3
```

**Re-run** when `iter-N/` already exists (crashed bench, or retry with new code):

```bash
python3 scripts/run_self_improve_bench.py run --force
# backs up existing iter-N/ to iter-N.retry-{timestamp}/ then re-runs
```

Verbose Groq logging: add `-v` to `run` or `iteration`.

---

## Per-iteration flow

1. Load prompts + bench from `iter-{latest_accepted_iter}/`
2. Groq thread: **Diagnose → Plan → Patch → Curate bench** (4 API calls, one accumulating thread)
3. Apply patch + bench curation to working copy
4. Sync prompts to gateway test files → reload (`compact_test=true`) → run 600-case bench → restore prod mode
5. Accept/reject (multi-metric gate with regression budget)
6. Write immutable `iter-{N}/` + update `meta.json`

### Accept gate

**Regression budget (hard reject)** — checked before any accept path:

- Any key metric drops **>8pp** (`off_topic`, `on_topic`, `jailbreak`, `switch_allowed`)
- Any **non-target** failure pattern increases by **>5** cases
- Pass **rate** drops **>1.5pp** (normalized for bench size changes)

**Accept** if budget passes and any of:

- Target pattern count decreased by **≥5** cases
- Key metric for **target section** improved **≥3pp** (correct section→metric mapping)
- Overall pass **rate** improved **≥1.5pp** with no single pattern regression **>3**

Plan phase must match `recommended_focus` unless top_pattern is switch-specific (one Groq retry enforced in code).

Accepted iterations with collateral damage add `do_not_repeat` entries and appear in `<accepted_tradeoffs>` for later iters.

### Promotion ranking (`meta.json`)

| Field | Meaning |
|-------|---------|
| `latest_accepted_iter` | Prompt/bench chain pointer for next iteration |
| `best_passes_iter` | Highest raw `passed` count (legacy `best_iter`) |
| `promotion_iter` | Highest **composite score** among accepted iters |
| `composite_scores` | Per-iter score map |

Composite score (default weights): `0.4×pass_rate + 0.25×switch + 0.20×off_topic + 0.15×jailbreak`

### Stop conditions

- `--max-iterations` reached (default **5**)
- **3 consecutive rejects** (`meta.consecutive_rejects`)
- Prompt size **>8k chars** after patch

---

## Groq context (iter ≥ 1)

After a reject, the next iteration diagnoses from the **last attempt**, not the original baseline.

| Block | Source |
|-------|--------|
| Prompts + bench copy | `iter-{latest_accepted_iter}/` |
| `<scores accepted_baseline>` | Accepted baseline report |
| `<failure_clusters>` | **`iter-{iteration-1}/report.json`** |
| `<regression_focus>` | Last attempt `delta.json` when previous iter rejected or accepted with collateral |
| `<recent_reject_history>` | Last 2–3 rejected iters |
| `<accepted_tradeoffs>` | Last 2 accepted iters with collateral metric/pattern regressions |
| `<last_attempt_scores>` | Last attempt report when it differs from baseline |

Inspect what Groq will see:

```bash
python3 scripts/run_self_improve_bench.py context --run-id caps-compact-v2 --iteration 4
```

Bench curation uses `<existing_bench_ids>`; new ids should look like `dom-si-4-001`. Duplicate ids are remapped on apply; if all adds skip, one Groq curation retry runs before the bench.

### Groq API notes

- **Structured Outputs** only: `response_format: json_schema`, `strict: true`
- `max_completion_tokens`: **8192** per phase (Groq API default is 1024)
- `reasoning_effort`: **medium** by default for gpt-oss-20b

---

## Directory layout

Root: `data/domain/bench/self-improve/` (local only, gitignored)

| Path | Purpose |
|------|---------|
| `runs.jsonl` | Registry of all runs |
| `active_run.json` | Default run when `--run-id` omitted |
| `runs/{run-id}/meta.json` | `latest_iter`, `latest_accepted_iter`, `best_passes_iter`, `promotion_iter`, `composite_scores` |
| `runs/{run-id}/lineage.jsonl` | Append-only iteration chain |
| `runs/{run-id}/integration_history.jsonl` | Prior integration verdicts for Groq context |
| `runs/{run-id}/iter-{N}/` | Immutable snapshot |
| `runs/{run-id}/final/` | Exported bundle from `finalize` |

### iter-{N}/ snapshot

| File | Contents |
|------|----------|
| `prompts/rules.json`, `overlay.json` | Prompts as benched |
| `bench/*.json` | Run-scoped bench fixtures |
| `messages.jsonl` | Full Groq 4-turn thread |
| `diagnosis.json`, `plan.json`, `patch.json`, `bench_curation.json` | Propose phases |
| `report.json`, `delta.json` | Bench results vs prior accepted |
| `integration.json`, `handoff.json` | Verdict + next-iter context |
| `changelog.md` | Human-readable summary |

Rejected iterations are fully saved but `latest_accepted_iter` does not advance.

---

## Manual promotion

After `finalize` (exports **`promotion_iter`** by default — composite-best among accepted):

```bash
python3 scripts/run_self_improve_bench.py finalize --run-id caps-compact-v2
# Highest raw pass count instead:
python3 scripts/run_self_improve_bench.py finalize --run-id caps-compact-v2 --best-passes
# Explicit iter:
python3 scripts/run_self_improve_bench.py finalize --run-id caps-compact-v2 --iteration 2
```

1. Review `final/manifest.json` and `final/report.json` (`export_iter`, `composite_score`, key metrics)
2. Copy `final/prompts/overlay.json` → `data/domain/compact_prompt_overlay.json` (and rules if changed)
3. Optionally merge `final/bench/` into `data/domain/bench/`
4. Reload gateway and run prod bench:

```bash
python3 scripts/tune_compact_prompt.py reload
PHI_GATEWAY_URL=http://localhost:8090 python3 scripts/run_classifier_bench.py
```

---

## CLI reference

```bash
python3 scripts/run_self_improve_bench.py init [--run-id ID] [--seed-run ID] [--force]
python3 scripts/run_self_improve_bench.py run [--run-id ID] [--max-iterations N] [--force] [-v]
python3 scripts/run_self_improve_bench.py iteration --number N [--run-id ID] [--force] [-v]
python3 scripts/run_self_improve_bench.py status [--run-id ID]
python3 scripts/run_self_improve_bench.py context --iteration N [--run-id ID]
python3 scripts/run_self_improve_bench.py finalize [--run-id ID] [--iteration N] [--best-passes]
python3 scripts/run_self_improve_bench.py runs list
python3 scripts/run_self_improve_bench.py runs use --run-id ID
```

---

## Runtime

| Phase | Duration (typical) |
|-------|-------------------|
| `init` iter-0 baseline bench | ~3 min (600 cases, 2 workers) |
| Each improvement iter | ~3 min bench + 4 Groq calls |
| Full `run --max-iterations 5` | ~15–25 min bench + Groq latency |

Gateway `PHI_CLASSIFY_CONCURRENCY=1` serializes classify on ~4 GiB GPUs; bench uses 2 parallel workers by default.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No active run. Run init first` | `python3 scripts/run_self_improve_bench.py init` |
| `iter-N/ already exists` | `run --force` or `iteration N --force` |
| `Gateway profile='medium'` (expected small) | Set `PHI_GATEWAY_PROFILE=small`, restart gateway |
| `PHI_GATEWAY_API_KEY is required` | Add to `.env.local`, `source` it |
| `GROQ_API_KEY is required` | Add to `.env.local` or Convex env |
| Run stops immediately, 0 iterations | `consecutive_rejects >= 3` in `meta.json`; fork with `--seed-run` or reset run |
| `run` continues wrong run | Check `active_run.json` or pass `--run-id`; use `runs use` |
| Incomplete iter (no `report.json`) | `run --force` to retry that iteration |
| Accepted but overall score down | Regression budget may be too loose; check `status` → `ranking`; use `finalize --best-passes` for max passes |
| `finalize` exports iter-0 not latest accepted | Default is `promotion_iter` (composite); use `--iteration` or check `promotion_iter` in `status` |

### Tests

```bash
cd scripts && python3 -m unittest compact_prompt_tune.self_improve.test_delta -v
```

---

## Deprecated

`scripts/compact_prompt_tune/self_improve.py` (one-shot Qwen POC) is replaced by this runner.
