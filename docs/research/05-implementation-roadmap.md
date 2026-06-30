# Implementation Roadmap for kyno

Phased rollout of the moderation gateway, mapped to kyno codebase integration points.

## Current State

```
User → ChatView.vue → useGroqChat.ts → convex/chat.ts → Groq API → response
```

No filtering at any stage. `sendMessage` in `convex/chat.ts` passes `args.messages` directly to Groq.

## Phase 1: Managed API Safety Check (1–2 days)

**Goal**: Block obvious unsafe content with zero model hosting.

Add OpenAI Moderation API (free) or equivalent as a pre-check in `sendMessage` before the Groq call.

```typescript
// convex/chat.ts — before fetch(GROQ_CHAT_URL, ...)
const moderation = await checkModeration(lastUserMessage.content)
if (moderation.flagged) {
  throw new ConvexError({
    code: 'MODERATION_BLOCK',
    category: moderation.topCategory,
    message: 'This message was flagged. Please rephrase.',
  })
}
```

**Frontend**: Handle `MODERATION_BLOCK` in `useGroqChat.ts`, show category-specific copy in `ChatView.vue`, preserve user input.

**Cost**: Free (API), ~200ms added latency.
**Models**: OpenAI Moderation API (no hosting).

## Phase 2: Self-Hosted Safety Gate (1 week)

**Goal**: Reduce latency and remove external API dependency for safety.

Deploy Llama Guard 3 (1B) as a sidecar service or via a compatible inference endpoint (Groq, Together, self-hosted vLLM).

Replace Phase 1 API call with guard model inference (~50ms).

**Integration**: Same `sendMessage` middleware, swap the backend call.

**Cost**: ~1.5 GB VRAM, cents per million tokens if self-hosted.
**Models**: [Llama-Guard-3-1B](https://huggingface.co/meta-llama/Llama-Guard-3-1B)

## Phase 3: Domain Router (1–2 weeks)

**Goal**: Limit the LLM to on-topic questions only.

Fine-tune ModernBERT-base on kyno-specific on-topic/off-topic examples.

```typescript
// convex/chat.ts — after safety check, before Groq call
const domain = await classifyDomain(lastUserMessage.content)
if (domain.label === 'off_topic') {
  throw new ConvexError({
    code: 'OFF_TOPIC',
    domain: 'kyno',
    suggestion: 'Try asking about ...',
  })
}
```

**Training**:
- Collect 500–1,000 on-topic/off-topic examples from product domain
- Fine-tune ModernBERT with standard HuggingFace Trainer (~1 hour, ~$1 spot GPU)
- Evaluate on held-out set, tune confidence threshold

**Frontend**: Handle `OFF_TOPIC` with helpful redirect copy (different from safety block).

**Cost**: <1 GB VRAM inference, ~$1 training.
**Models**: [ModernBERT-base](https://huggingface.co/answerdotai/ModernBERT-base)

## Phase 4: Custom Policy Fine-Tune (2–3 weeks)

**Goal**: Handle domain-specific policies that guard models miss.

Fine-tune Llama-3.2-3B with QDoRA + classification head on ~3,000 synthetic examples:

1. Define kyno policy taxonomy (extend Level 1/2 from best practices doc)
2. Generate synthetic training data via frontier model + active learning
3. Train with QDoRA (rank 16, 3 epochs, ~$2–5)
4. Evaluate on ToxicChat + custom eval set
5. Distill into ModernBERT for production speed

**Cost**: ~$5–15 total (data + training).
**Models**: Llama-3.2-3B-Instruct → distill to ModernBERT.

## Phase 5: Output Filter + Observability (1 week)

**Goal**: Catch harmful LLM responses; enable monitoring and HITL.

1. Run safety classifier on assistant response before returning to user
2. Add audit logging: `{ input_hash, model_version, scores, action, timestamp }`
3. Route medium-confidence cases to review queue
4. Dashboard for false positive rate, category distribution, model drift

**Integration**: After Groq response in `sendMessage`, before returning `{ content, model }`.

## Architecture After All Phases

```
User message
    │
    ▼
ChatView.vue / useGroqChat.ts
    │
    ▼
convex/chat.ts :: sendMessage
    │
    ├─ [Phase 1/2] Safety gate (Llama Guard 3 1B)     → MODERATION_BLOCK
    ├─ [Phase 3]   Domain router (ModernBERT)          → OFF_TOPIC
    ├─ [existing]  Groq API call                       → LLM response
    └─ [Phase 5]   Output filter (Llama Guard 3 1B)   → redact/block
    │
    ▼
Response to user
```

## Response Codes

Extend `sendMessage` return type or error codes:

| Code | Phase | Meaning | User action |
|------|-------|---------|-------------|
| `MODERATION_BLOCK` | 1+ | Safety violation | Edit and retry |
| `OFF_TOPIC` | 3+ | Outside product domain | See suggestion |
| `UNDER_REVIEW` | 5 | Low confidence, HITL | Wait or retry |
| Success | — | Safe + on-topic | Show LLM response |

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Safety model | Llama Guard 3 1B | Cheapest viable guard, English chat |
| Domain model | ModernBERT-base | Sub-10ms, fixed labels |
| Fine-tune method | QDoRA + classification head | Best cost/accuracy for custom policies |
| Training data | ~3k synthetic via active learning | Quality over quantity |
| Output filter | Same guard model as input | Consistency, no extra model to host |
| License preference | Apache 2.0 models | No MAU caps for commercial SaaS |

## Files to Modify

| File | Changes |
|------|---------|
| `convex/chat.ts` | Add gateway middleware in `sendMessage` handler |
| `convex/moderation.ts` (new) | Safety check, domain classify, output filter functions |
| `src/composables/useGroqChat.ts` | Handle new error codes |
| `src/views/ChatView.vue` | Blocked/off-topic UI states, preserve input on block |
