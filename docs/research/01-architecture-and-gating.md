# Architecture and Gating Patterns

How to use task-agnostic open-weight models as a gateway that limits the main LLM interface to safe, domain-specific questions.

## Problem

The main LLM in kyno (`convex/chat.ts` → Groq) is powerful but expensive and unconstrained. Every user message currently reaches it unfiltered. A gateway model should:

- Block unsafe content before it reaches the LLM
- Reject off-topic queries without wasting LLM tokens
- Return structured decisions (block / route / allow) in <200ms

## Architecture Patterns

### Cascade / routing (recommended)

A small classifier runs first. Only passing messages proceed to the main LLM.

| Pros | Cons |
|------|------|
| Extremely cost-effective | Router is a single point of failure |
| Reduces latency for rejected queries | Requires high recall on safety to avoid missing harms |
| Simple to reason about | Needs separate domain vs safety handling |

### Multi-LoRA on shared base

One base model (e.g., ModernBERT or Qwen) with task-specific LoRA adapters for safety, intent, and PII detection. A single forward pass can evaluate multiple tasks.

| Pros | Cons |
|------|------|
| High memory efficiency | Requires specialized serving (vLLM, Ray) |
| Shared base model computation | Adapter hot-swap adds ops complexity |
| Easy to add new tasks | |

### Guardrails frameworks

Event-driven runtimes like [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) execute programmable "rails" in Colang. Highly customizable for multi-turn dialogue but adds configuration complexity and latency if not optimized.

### Centralized gateway proxy

Services like [LiteLLM](https://github.com/BerriAI/litellm) or Cloudflare AI Gateway sit between apps and LLM providers. Good for observability and key management but adds a network hop.

## Recommended Pipeline for kyno

A three-tier filtering architecture balances cost, accuracy, and latency:

```
User message
    │
    ▼
┌─────────────────────────┐
│ Tier 1: Fast Input Rails │  Llama Guard 3 (1B) or regex pre-filter
│ Safety + prompt injection│  Action: reject unsafe → static response
└────────────┬────────────┘
             │ pass
             ▼
┌─────────────────────────┐
│ Tier 2: Domain Router    │  ModernBERT or Llama-3.2-1B + classification head
│ Intent / on-topic check  │  Action: reject off-topic → domain redirect
└────────────┬────────────┘
             │ pass
             ▼
┌─────────────────────────┐
│ Main LLM (Groq)          │  llama-3.3-70b-versatile (existing)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Tier 3: Output Rails     │  Llama Guard 3 or OpenAI Moderation API
│ Response safety check    │  Action: block or redact before display
└─────────────────────────┘
```

### Tier 1: Safety (the gate)

Use a pre-trained guard model rather than fine-tuning from scratch:

- **Llama Guard 3 (1B)**: ~50ms latency, ~1.5 GB VRAM. Best for English-only, ultra-low cost.
- **Qwen3-Guard (4B)**: ~100ms latency, ~3 GB VRAM. Best for multilingual (119 languages).
- **ShieldGemma (2B)**: High precision, low false positives. Good when over-blocking is costly.

Reject immediately with a static response. Do not call the main LLM.

### Tier 2: Domain routing (the filter)

This is what limits the LLM interface. A classification head on ModernBERT or a small instruct model determines whether the query is on-topic for kyno's domain.

Output labels example: `on_topic`, `off_topic`, `needs_clarification`.

Route off-topic queries to a handler that explains scope and suggests alternatives — never to the main LLM.

### Tier 3: Output filter

Re-scan the LLM response for policy violations, PII leakage, or hallucinated unsafe content before returning to the user. Can run async if latency is acceptable.

## Interface Limiting

The gateway's core job is constraining what the main LLM sees:

| Decision | Main LLM called? | User sees |
|----------|-----------------|-----------|
| Safe + on-topic | Yes | LLM response |
| Unsafe (safety block) | No | "Flagged for [category]. Rephrase to continue." |
| Off-topic (domain block) | No | "I'm specialized in [domain]. Try asking about [example]." |
| Low confidence | No (HITL queue) | "Your message is being reviewed." |

The main LLM never receives blocked messages. This saves tokens, reduces attack surface, and keeps the LLM focused on domain work.

## Cost / Accuracy Tradeoffs

| Approach | Latency | Cost | Accuracy |
|----------|---------|------|----------|
| Regex pre-filter | <10ms | Free | Catches known patterns only |
| Small guard (1B) | 10–50ms | Cents/M tokens | Good for obvious harms |
| Guard + domain (1B + encoder) | 50–150ms | Low | Production-grade for most apps |
| Managed API (OpenAI Moderation) | 200ms+ | Free | Zero infra, privacy concern |
| Custom fine-tune | 50–200ms | $1–5 training | Highest domain accuracy |

## References

- [Llama Guard 3 model card](https://www.llama.com/docs/model-cards-and-prompt-formats/llama-guard-3/)
- [ShieldGemma model card](https://ai.google.dev/gemma/docs/shieldgemma/model_card)
- [ModernBERT](https://huggingface.co/answerdotai/ModernBERT-base)
- [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails)
- [vLLM Semantic Router](https://github.com/vllm-project/semantic-router)
- [LoRA-Guard (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.656.pdf)
- [LiteLLM gateway](https://github.com/BerriAI/litellm)

## kyno Integration Point

The gateway belongs in `convex/chat.ts` inside the `sendMessage` handler, before the `fetch(GROQ_CHAT_URL, ...)` call at line 68. Frontend handling for blocked/off-topic states goes in `src/views/ChatView.vue` and `src/composables/useGroqChat.ts`.
