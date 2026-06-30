# Task-Agnostic LM Moderation Gateway — Research

Research on training and deploying open-weight, task-agnostic language models as a moderation and domain-routing gateway for kyno. The gateway sits before the main LLM (Groq) and limits what reaches it: only safe, on-topic messages proceed.

## Documents

| Document | Topic |
|----------|-------|
| [01-architecture-and-gating.md](./01-architecture-and-gating.md) | Pipeline design, interface limiting, cascade patterns |
| [02-open-weight-models.md](./02-open-weight-models.md) | Model selection, hardware, licensing |
| [03-fine-tuning-methods.md](./03-fine-tuning-methods.md) | QDoRA, data requirements, training costs |
| [04-moderation-best-practices.md](./04-moderation-best-practices.md) | Taxonomy, datasets, production patterns, UX |
| [05-implementation-roadmap.md](./05-implementation-roadmap.md) | Phased rollout for kyno |

## Executive Summary

kyno currently sends raw user input from `convex/chat.ts` directly to Groq with no filtering. The recommended approach is a **defense-in-depth gateway** using cheap open-weight models before the main LLM call.

### Recommended stack

1. **Deterministic pre-filter** (<10ms): regex for PII patterns, known jailbreak strings, blocked keywords.
2. **Safety classifier** (<200ms): Llama Guard 3 (1B) for English-only, or Qwen3-Guard (4B) for multilingual. Fine-tune on WildGuardMix if domain-specific policies are needed.
3. **Domain classifier** (<200ms): ModernBERT-base for fast intent/domain routing, or Llama-3.2-1B with a classification head for higher accuracy.
4. **Main LLM**: existing Groq path — only reached when both classifiers pass.
5. **Output filter**: re-run safety check on assistant responses before display.

### Training path

Start with pre-trained guard models (zero training cost). When custom policies are required, fine-tune Llama-3.2-3B using **QDoRA with a classification head** on ~3,000 synthetic examples (~$1–5 compute). Distill into ModernBERT for production throughput.

### Cost profile

| Component | Inference cost | Fine-tune cost |
|-----------|---------------|----------------|
| Llama Guard 3 1B | ~1.5 GB VRAM, <50ms | N/A (use as-is) |
| ModernBERT domain router | <1 GB VRAM, <10ms | ~$1 spot GPU, 1 hour |
| Llama-3.2-3B custom policy | ~3 GB VRAM, <100ms | ~$1–5 spot GPU, 2–4 hours |

### Key principle

Use **classification heads**, not free-form JSON generation, for all gateway decisions. Encoders (ModernBERT) for speed; small decoders (Llama 1B–3B) for reasoning-heavy domain routing; pre-trained guards for safety.
