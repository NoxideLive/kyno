# Self-improve bench

Automated multi-iteration compact prompt tuning. **Groq** (`openai/gpt-oss-20b`) proposes prompt patches and bench curation; the local **phi-gateway** (Qwen2.5-1.5B small profile) runs the 600-case classifier bench.

Production fixtures (`data/domain/bench/*.json`, `compact_prompt_overlay.json`) are never modified. Each run stores immutable snapshots under `data/domain/bench/self-improve/runs/{run-id}/`.

See also: [compact-prompt-tuning-flow.md](compact-prompt-tuning-flow.md) for the manual 5-cycle operator loop.

## Preconditions

- Gateway: `curl -sf http://localhost:8090/health` → `profile=small`, `phi_loaded=true`
- `PHI_GATEWAY_API_KEY` for bench reload
- `GROQ_API_KEY` for propose phases (iter ≥ 1) — host env, `.env.local`, or Convex (`npx convex env get GROQ_API_KEY`)
- Groq uses **Structured Outputs** (`response_format: json_schema`, `strict: true`) on `openai/gpt-oss-20b`
- `max_completion_tokens`: **8192** per phase (Groq API default is 1024; model max output is 65536)
- `reasoning_effort`: **medium** (Groq default for gpt-oss-20b); override via `SELF_IMPROVE_GROQ_REASONING_EFFORT`
- Optional: `SELF_IMPROVE_GROQ_MODEL=openai/gpt-oss-20b` (default)

```bash
export PHI_GATEWAY_URL=http://localhost:8090
set -a && source .env.local && set +a
```

## Quick start

```bash
# Create run (cold-start empty prompts + full 600-case baseline bench)
python3 scripts/run_self_improve_bench.py init

# Explicit run ID
python3 scripts/run_self_improve_bench.py init --run-id caps-compact-v2

# Fork from prior run
python3 scripts/run_self_improve_bench.py init --run-id fork-v2 --seed-run 20260701-143022

# Run up to 5 iterations (stops after 3 consecutive rejects)
python3 scripts/run_self_improve_bench.py run --run-id caps-compact-v2

# Single iteration
python3 scripts/run_self_improve_bench.py iteration --run-id caps-compact-v2 --number 1

# Export best iteration for manual prod promotion
python3 scripts/run_self_improve_bench.py finalize --run-id caps-compact-v2
```

## Directory layout

Root: `data/domain/bench/self-improve/`

| Path | Purpose |
|------|---------|
| `runs.jsonl` | Registry of all runs |
| `active_run.json` | Default run when `--run-id` omitted |
| `runs/{run-id}/meta.json` | `latest_iter`, `latest_accepted_iter`, `best_iter` |
| `runs/{run-id}/lineage.jsonl` | Append-only iteration chain |
| `runs/{run-id}/integration_history.jsonl` | Prior integration verdicts for Groq context |
| `runs/{run-id}/iter-{N}/` | Immutable snapshot (prompts, bench, report, handoff) |
| `runs/{run-id}/final/` | Exported bundle from `best_iter` |

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

Rejected iterations are fully saved but `latest_accepted_iter` does not advance. The next iteration loads prompts/bench from the last accepted snapshot.

### Groq context sources (iter ≥ 1)

| Block | Source |
|-------|--------|
| Prompts + bench copy | `iter-{latest_accepted_iter}/` |
| `<scores accepted_baseline>` | Accepted baseline report |
| `<failure_clusters>` | **`iter-{iteration-1}/report.json`** (last attempt) |
| `<regression_focus>` | Last attempt `delta.json` when previous iter rejected |
| `<recent_reject_history>` | Last **2–3 rejected** iters (handoff + delta summary) |
| `<last_attempt_scores>` | Last attempt report when it differs from baseline |

Inspect what Groq will see:

```bash
python3 scripts/run_self_improve_bench.py context --run-id fork-test --iteration 4
```

Bench curation uses `<existing_bench_ids>` and requires ids like `dom-si-4-001`. Duplicate ids are remapped on apply; if all adds skip, one Groq curation retry runs before the bench.

## Per-iteration flow

1. Load base from `iter-{latest_accepted_iter}/`
2. Groq thread: **Diagnose → Plan → Patch → Curate bench** (4 API calls, one accumulating thread)
3. Apply patch + bench curation to working copy
4. Bench via gateway test mode (`compact_test` reload)
5. Accept/reject (pattern-primary gate)
6. Write immutable `iter-{N}/` + update `meta.json`

### Accept gate (pattern-primary)

Accept if any of:

- Target pattern count decreased by ≥5 cases
- Key metric for target section improved ≥3pp
- Overall `passed` improved by ≥3 with no single pattern regression >3

Stop conditions: `--max-iterations` (default 5), 3 consecutive rejects, or prompt size >8k chars.

## Manual promotion

After `finalize`:

1. Review `final/manifest.json` and `final/report.json`
2. Copy `final/prompts/` → production compact prompt paths
3. Optionally review `final/bench/` before merging into `data/domain/bench/`
4. Reload gateway and run prod bench

## CLI reference

```bash
python3 scripts/run_self_improve_bench.py runs list
python3 scripts/run_self_improve_bench.py runs use --run-id caps-compact-v2
python3 scripts/run_self_improve_bench.py status --run-id caps-compact-v2
python3 scripts/run_self_improve_bench.py context --run-id caps-compact-v2 --iteration 2
python3 scripts/run_self_improve_bench.py finalize --run-id caps-compact-v2 --iteration 3
```

## Runtime

- Baseline bench (iter 0): ~3 min for 600 cases
- Each improvement iteration: ~3 min bench + 4 Groq calls

## Deprecated

`scripts/compact_prompt_tune/self_improve.py` (one-shot Qwen POC) is replaced by this runner.
