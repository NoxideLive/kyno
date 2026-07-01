# Compact prompt tuning flow

Operator playbook for the 5-cycle compact-prompt tuning loop on the **small** profile.

For automated multi-iteration tuning with Groq propose + immutable run snapshots, see **[self-improve-bench.md](self-improve-bench.md)** (pre-run checklist, `init` vs `run`, troubleshooting).

## Preconditions

- Gateway running: `curl -sf http://localhost:8090/health` → `profile=small`, `phi_loaded=true`
- Env: `PHI_GATEWAY_PROFILE=small`, `PHI_GATEWAY_PROMPT_VARIANT=compact` (or `auto`)
- `PHI_GATEWAY_API_KEY` set (host scripts + reload)
- Baseline seeded at `data/domain/bench/tuning/iter-0-report.json` (457/600)

```bash
export PHI_GATEWAY_URL=http://localhost:8090
# Load key from .env.local if needed:
set -a && source .env.local && set +a
```

## Subagent model policy

**All Task subagents MUST use `model: composer-2.5-fast`.** Pass explicitly on every Task invocation.

## Artifacts

| Path | Purpose |
|------|---------|
| `data/domain/compact_prompt_overlay.json` | Primary tuning surface (examples prepended to compact prompts) |
| `services/phi-gateway/domain_prompt.py` | `COMPACT_RULES`, `COMPACT_*_LIMIT` |
| `services/phi-gateway/jailbreak_prompt.py` | `COMPACT_RULES`, `COMPACT_*_LIMIT` |
| `data/domain/bench/tuning/iter-{n}-report.json` | Bench output per cycle |
| `data/domain/bench/tuning/iter-{n}-changelog.md` | Improver notes per cycle |
| `data/domain/bench/tuning/state.json` | Cycle scores and paths |
| `data/domain/bench/tuning/summary.jsonl` | One JSON line per cycle |

**Do not edit** `data/domain/prompt_examples.json` or `data/domain/jailbreak_examples.json` during tuning.

## CLI

```bash
python3 scripts/tune_compact_prompt.py bench --iteration N
python3 scripts/tune_compact_prompt.py analyze --report data/domain/bench/tuning/iter-N-report.json
python3 scripts/tune_compact_prompt.py reload
python3 scripts/tune_compact_prompt.py status
```

## Parent loop (5 cycles, sequential)

```
for N in 1..5:
  summary_N = Task(BenchSubagent, model=composer-2.5-fast, iteration=N)
  changelog_N = Task(ImproverSubagent, model=composer-2.5-fast, report=summary_N.report_path)
  if summary_N.delta_vs_prior.passed < -12: warn user
```

After cycle 5: produce comparison table from `summary.jsonl`.

### Bench subagent (`subagent_type: shell`, `model: composer-2.5-fast`)

1. Confirm gateway health (`profile=small`, `phi_loaded=true`)
2. `PHI_GATEWAY_URL=http://localhost:8090 python3 scripts/tune_compact_prompt.py bench --iteration N`
3. `python3 scripts/tune_compact_prompt.py analyze --report data/domain/bench/tuning/iter-N-report.json`
4. If N>1, compute delta vs `iter-{N-1}-report.json`

Return structured JSON: iteration, passed/total, suites, key_metrics, delta_vs_prior, top_failure_patterns, report_path.

**Do not edit prompt files.**

### Improver subagent (`subagent_type: generalPurpose`, `model: composer-2.5-fast`)

1. Read failures via `analyze`; for switch cases resolve history from `data/domain/bench/switch.json` by `id`
2. Edit overlay / compact rules / limits (allowed files only)
3. `python3 scripts/tune_compact_prompt.py reload`
4. Write `data/domain/bench/tuning/iter-N-changelog.md`
5. Append cycle notes to state if needed

Priorities:

- **Switch allowed recall** (off→on recovery conversation examples)
- **Jailbreak safe FP** (vehicle-analogy safe examples vs jailbreak)
- Hold jailbreak recall ≥90%, off_topic recall ≥55%

Return: changelog path, files touched, prompt char count estimate.

## Gateway reload

```bash
curl -sf -X POST http://localhost:8090/admin/reload-prompts \
  -H "Authorization: Bearer $PHI_GATEWAY_API_KEY"
```

Or: `python3 scripts/tune_compact_prompt.py reload`

## Stop conditions

- Overall regression >2pp without switch recovery
- Prompt size >8k chars (`build_domain_system_prompt("compact")` length)

## Success criteria

| Metric | Baseline (iter 0) | Target after 5 cycles |
|--------|-------------------|------------------------|
| Overall pass | 457/600 | ≥470/600 |
| Switch allowed recall | 54% | ≥75% |
| Domain off_topic recall | 50% | ≥55% |
| Jailbreak recall | 93% | ≥90% |

## Stall detection

If a bench run appears stuck:

```bash
ps aux | rg 'run_classifier_bench|tune_compact_prompt|phi-gateway'
```

Check terminal output in Cursor terminals folder. A running bench python process with advancing CPU/time is **not** stalled (~3 min per 600-case run). Intervene only if process is dead, gateway returns 503, or no PID after expected start.

## Estimated runtime

~3 min/bench × 5 ≈ 15 min bench time + improver edit time.
