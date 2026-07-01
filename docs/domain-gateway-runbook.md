# Domain gateway runbook

Single **phi-gateway** container: bare Phi-4-mini-instruct loads once on **GPU** for **classification** (Convex) and **CAPS data pipeline** (admin).

## Manual vs pipeline

| Manual | Same phi-gateway server |
|--------|-------------------------|
| Download CAPS PDFs | — |
| Edit `data/domain/prompt_examples.json` | — |
| Edit `data/domain/jailbreak_examples.json` | — |
| Edit `data/domain/eval/*.jsonl` | — |
| Run eval CLI | — |
| Boot gateway | `POST /pipeline/rebuild` (via CLI or curl) |

## Requirements

- NVIDIA GPU with **4 GB+ VRAM** (Phi 4-bit)
- Docker Compose v2
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (`nvidia-smi` works inside containers)

---

## Boot (Docker Compose)

Dev stack (Vite + Convex + phi-gateway):

```bash
cd /code/riv/kyno
# See docs/local-dev-docker.md — shared .env.local for all services
./scripts/dev-init.sh
```

Phi gateway only:

```bash
docker compose --profile dev up --build phi-gateway
```

Verify GPU:

```bash
docker compose --profile dev run --rm phi-gateway python -c "import torch; print('cuda:', torch.cuda.is_available())"
```

Wait until healthy (first boot downloads model weights — can take several minutes):

```bash
curl -s http://localhost:8090/health | jq .
# phi_loaded: true, status: ok, gpu: { device, vram_gib }
```

`/health` returns **503** until Phi is loaded on CUDA. The entrypoint exits immediately if CUDA is unavailable.

Stop:

```bash
docker compose down
```

Model weights cache persists in Docker volume `phi_hf_cache`. Domain data lives in bind-mounted `./data`.

---

## Host scripts

PDF download, pipeline CLI, and eval run on the host and call the gateway:

```bash
export PHI_GATEWAY_URL=http://localhost:8090
export PHI_GATEWAY_API_KEY=your-secret

python3 scripts/pull_syllabus.py --caps-only --all-grades --skip-existing
python3 scripts/run_domain_pipeline.py
python3 scripts/run_classifier_bench.py
python3 scripts/tune_compact_prompt.py bench --iteration 1   # compact tuning (see docs/compact-prompt-tuning-flow.md)
python3 scripts/eval_domain_classifier.py
python3 scripts/eval_jailbreak_classifier.py   # alias: --suite jailbreak
```

### Manual — refresh CAPS PDFs

When DBE publishes updated policy documents:

```bash
python3 scripts/pull_syllabus.py --caps-only --all-grades --skip-existing
```

Edit few-shot examples by hand when needed:

```bash
$EDITOR data/domain/prompt_examples.json
$EDITOR data/domain/jailbreak_examples.json
```

### Pipeline — rebuild topic data

Gateway must be running. Uses the **same** Phi instance as classify.

```bash
python3 scripts/run_domain_pipeline.py
```

Or curl:

```bash
curl -s -X POST http://localhost:8090/pipeline/rebuild \
  -H "Authorization: Bearer $PHI_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

Writes:

- `data/syllabus/phases/*/mathematics/caps-sections.json`
- `data/domain/caps_topic_list.json`
- `data/domain/pipeline_report.json`

Does **not** modify `prompt_examples.json` or `jailbreak_examples.json`. Prompt caches reload automatically.

---

## Convex

```bash
npx convex env set PHI_GATEWAY_URL http://<host-ip>:8090
npx convex env set DOMAIN_GATEWAY_ENABLED true
# optional: npx convex env set PHI_GATEWAY_API_KEY ...
```

Use the machine's LAN IP (not `localhost`) if Convex runs in the cloud.

Blocking rule (single `POST /classify/message` call before Groq):

- Block if jailbreak stage returns `jailbreak_attempted`
- Else block if domain stage (with history) returns `off_topic`
- Allow only when jailbreak is `safe` **and** domain is `on_topic`
- User-facing message is unified (`OFF_TOPIC`) — jailbreak vs off-topic is internal only

Fail-closed when gateway enabled but unreachable.

---

## Classifier bench (gate regression)

Unified benchmark for jailbreak, domain on/off, and topic-switch leaks. Fixtures are **JSON** (not JSONL):

```
data/domain/bench/
  bench.config.json
  jailbreak.json    # safe, jailbreak_attempted (≥100 each)
  domain.json       # on_topic, off_topic (≥100 each)
  switch.json       # allowed, blocked (≥100 each)
  report.json       # last run output
```

**Switch history shapes** (match product persistence):

- **`on_to_off` (blocked):** prior persisted CAPS user + assistant turn, latest message goes off-topic.
- **`off_to_on` (allowed):** one or two **blocked user-only** lines (client optimistic state after gate reject — no assistant reply was ever stored), latest message returns to CAPS.

Regenerate fixtures (deterministic seed):

```bash
python3 scripts/generate_classifier_bench.py
```

Run all suites in parallel (auto workers = min(cases, 64)):

```bash
export PHI_GATEWAY_URL=http://localhost:8090
python3 scripts/run_classifier_bench.py
python3 scripts/run_classifier_bench.py --suite switch
python3 scripts/run_classifier_bench.py --workers 64
```

Report: `data/domain/bench/report.json`. Exit code 0 only if every case passes.

### Automated self-improve loop

For Groq-driven multi-iteration compact prompt tuning with immutable run snapshots, see **[self-improve-bench.md](self-improve-bench.md)**.

Prerequisites: gateway on **`small`** profile, `PHI_GATEWAY_API_KEY`, `GROQ_API_KEY`, production bench fixtures in `data/domain/bench/`.

```bash
python3 scripts/run_self_improve_bench.py init --run-id my-run
python3 scripts/run_self_improve_bench.py run --run-id my-run
```

---

## Manual eval (threshold sweep)

Domain threshold tuning uses separate JSONL regression sets — not the bench:

```bash
export PHI_GATEWAY_URL=http://localhost:8090
python3 scripts/eval_domain_classifier.py
```

Report: `data/domain/eval/eval_report.json`. Tune `prompt_examples.json` from failures; `DOMAIN_CONFIDENCE_THRESHOLD` in eval config is for threshold sweeps only, not chat blocking.

---

## Environment

Set in `.env.local` or the shell before `docker compose up`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PHI_GATEWAY_API_KEY` | *required* | Pipeline routes + optional classify auth |
| `PHI_GATEWAY_PORT` | `8090` | Host port mapping |
| `PHI_GATEWAY_PROFILE` | `medium` | `small` \| `medium` \| `large` preset (HF model ids per role) |
| `PHI_GATEWAY_PROMPT_VARIANT` | `auto` | `auto` (compact on `small`) \| `full` \| `compact` classify prompts |
| `PHI_GATEWAY_JAILBREAK_MODEL` | *(profile)* | HF `org/name` override for jailbreak |
| `PHI_GATEWAY_DOMAIN_MODEL` | *(profile)* | HF `org/name` override for domain |
| `PHI_GATEWAY_PIPELINE_MODEL` | *(profile)* | HF `org/name` override for pipeline generation |
| `PHI_GATEWAY_GUARD_MODELS` | — | Comma-separated HF ids forced to guard adapter |
| `HF_TOKEN` | — | HuggingFace token for gated models |
| `PHI_MAX_SEQ_LENGTH` | `2048` | Pipeline generation context |
| `PHI_CLASSIFY_MAX_SEQ_LENGTH` | `2048` | Classify forward pass truncation |
| `PHI_CLASSIFY_CONCURRENCY` | `1` | Max concurrent classify requests |
| `DOMAIN_CONFIDENCE_THRESHOLD` | `0.4` | Eval threshold sweep only (not chat blocking) |
| `PHI_LOAD_4BIT` | `true` | 4-bit quantization |

Inside the container: `KYNO_REPO_ROOT=/app`, repo bind-mounted at `/app` (including `data/`).

---

## API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | — | Ready probe (503 until GPU + Phi ready) |
| POST | `/classify/message` | optional | **Convex chat gate** (parallel jailbreak + domain) |
| POST | `/classify/jailbreak` | optional | Jailbreak stage only (eval) |
| POST | `/classify/domain` | optional | Domain stage only — binary on/off (eval) |
| GET | `/domain-spec` | — | Scope summary |
| POST | `/pipeline/rebuild` | **required** | CAPS extract + topic list |
| GET | `/pipeline/status` | **required** | Last pipeline report |

---

## Troubleshooting

**Container exits on start:** CUDA not visible. Install NVIDIA Container Toolkit and confirm:

```bash
docker compose --profile dev run --rm phi-gateway python -c "import torch; print(torch.cuda.is_available())"
```

**Health stuck on 503:** First model download or slow GPU. Check logs: `docker compose --profile dev logs -f phi-gateway`.

**CUDA OOM during classification:** Logs show `CUDA OOM during classification` and chat returns "Domain check is temporarily unavailable."

- **Cause:** 4 GiB-class GPUs are tight for Phi-4-mini 4-bit plus ~1700-token domain classify prompts. Under load, forward passes need ~640 MiB activation memory on top of ~2.7 GiB model weights.
- **Fix:** Keep `PHI_CLASSIFY_CONCURRENCY=1` (compose default). Recreate the container after env changes — `restart` alone does not pick up compose env:

```bash
docker compose --env-file .env.local up --build -d phi-gateway
```

- **Verify:** Run bench with parallel workers; logs should show no OOM:

```bash
PHI_GATEWAY_URL=http://localhost:8090 python3 scripts/run_classifier_bench.py --workers 4
```

`/health` includes `profile`, `roles`, `models_loaded`, and `gpu.vram_warning` when total VRAM is under 4 GiB.

**Pipeline model swap:** When `PHI_GATEWAY_PIPELINE_MODEL` differs from classify models (e.g. `small` profile + Phi pipeline), `/pipeline/rebuild` temporarily evicts classify models, loads the pipeline model, then restores classify models. Classify returns 503 during the swap.

**Large profile:** Set `HF_TOKEN` for `meta-llama/Llama-Guard-3-1B`.

**Convex cannot reach gateway (cloud prod):** Use host IP and open port 8090. In local dev, env sync sets `PHI_GATEWAY_URL=http://phi-gateway:8090` automatically.

---

## Compact prompt reload (tuning)

After editing `data/domain/compact_prompt_overlay.json` or compact rules in `domain_prompt.py` / `jailbreak_prompt.py`, reload without restarting the container:

```bash
curl -sf -X POST http://localhost:8090/admin/reload-prompts \
  -H "Authorization: Bearer $PHI_GATEWAY_API_KEY"
```

Or:

```bash
python3 scripts/tune_compact_prompt.py reload
```

Requires `PHI_GATEWAY_API_KEY`. Full tuning workflow: [`docs/compact-prompt-tuning-flow.md`](compact-prompt-tuning-flow.md).

---

## Archived LoRA pipeline

See [`archive/domain-lora-pipeline/README.md`](../archive/domain-lora-pipeline/README.md).
