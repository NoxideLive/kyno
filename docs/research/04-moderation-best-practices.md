# Moderation Best Practices

Production patterns for chat moderation, domain routing, datasets, and user experience.

## Moderation Taxonomy

Use a three-level hierarchy. Broad domains at the top, actionable leaf labels at the bottom.

### Level 1: Content safety domains

| Domain | Covers |
|--------|--------|
| **Toxicity** | Harassment, hate speech, threats, abusive language |
| **Sensitive topics** | Self-harm, sexual content, graphic violence, illegal acts |
| **System security** | Prompt injection, jailbreak, instruction-hierarchy violations |
| **Data privacy** | PII (emails, phones, credentials), sensitive internal data |

### Level 2: Operational categories

Examples under System Security: goal hijacking, prompt leaking, indirect injection via URLs/documents.

Examples under Toxicity: identity-based hate, sexual harassment, microaggressions.

### Level 3: Leaf labels

Fine-grained labels for specific UX feedback. "This message contains a phone number" is more helpful than "This message is unsafe."

## Multi-Stage Pipeline

Defense-in-depth is the industry standard:

```
Stage 1: Deterministic pre-filter     (<10ms, sync)
  └─ Regex: jailbreak strings, PII patterns, blocked keywords
  └─ Hash-matching: known-bad snippets

Stage 2: ML safety classifier         (<200ms, sync)
  └─ Llama Guard 3 / WildGuard / DeBERTa-v3-small
  └─ Block if confidence > high threshold
  └─ Flag for review if confidence is medium

Stage 3: Domain classifier            (<200ms, sync)
  └─ ModernBERT or small LLM
  └─ Route to main LLM if on-topic
  └─ Route to off-topic handler otherwise

Stage 4: Output filter                (async or sync)
  └─ Scan LLM response for policy violations, PII leakage
  └─ Block or redact before display
```

Keep synchronous pre-filters under 200ms total to avoid degrading chat UX.

## Datasets

| Dataset | Size | Best for | Link |
|---------|------|----------|------|
| **ToxicChat** | 10K | In-the-wild toxicity evaluation | [d-llm/toxic-chat](https://huggingface.co/datasets/d-llm/toxic-chat) |
| **WildGuardMix** | 92K | Training: 13 risk categories incl. jailbreaks | [allenai/wildguardmix](https://huggingface.co/datasets/allenai/wildguardmix) |
| **Aegis 2.0** | 34K | Human-annotated, 12-category taxonomy | [NAACL 2025 paper](https://aclanthology.org/2025.naacl-long.306/) |
| **HarmBench** | Benchmark | Adversarial safety evaluation | [centerforaisafety/HarmBench](https://github.com/centerforaisafety/HarmBench) |

**Training**: WildGuardMix for safety model fine-tuning.
**Evaluation**: ToxicChat for in-the-wild toxicity; HarmBench for adversarial robustness.

For domain classification, create a custom dataset of on-topic/off-topic examples from your product domain. 500–1,000 labeled examples is sufficient for ModernBERT fine-tuning.

## Production Best Practices

### Confidence thresholds

Use per-category thresholds, not a single global cutoff:

- Higher **precision** for harassment (avoid over-blocking casual language)
- Higher **recall** for legal risks (CSAM, credible threats)
- Medium-confidence band (0.4–0.7): route to human review, not auto-block

### Human-in-the-loop (HITL)

Route low-confidence or high-impact cases to a review queue. Provide reviewers with:

- Original input
- Model scores per category
- Model version used
- Recommended action

### Audit logging

Maintain append-only logs of every gateway decision:

```
{ timestamp, input_hash, model_version, scores, action, category }
```

Required for compliance (DSA, etc.) and for detecting model drift over time.

### Latency budget

| Stage | Budget |
|-------|--------|
| Deterministic pre-filter | <10ms |
| Safety classifier | <100ms |
| Domain classifier | <50ms |
| Total gateway | <200ms |
| Output filter | async OK |

## UX: Safety Blocks vs Domain Mismatches

Users must understand *why* their message was rejected. Different triggers need different copy and actions.

| | Safety block | Domain mismatch |
|---|-------------|-----------------|
| **Trigger** | Policy violation | Query outside product scope |
| **Copy** | "Flagged for [category]. Rephrase to continue." | "I'm specialized in [domain]. I can't help with [topic], but I can answer [example]." |
| **User action** | Edit and retry (preserve input) | Redirect to correct domain or support |
| **Tone** | Firm, transparent | Helpful, boundary-setting |

### Implementation in kyno

- **Safety block**: return error from `sendMessage` with `{ code: 'MODERATION_BLOCK', category, message }`. Frontend in `ChatView.vue` shows the flag reason and preserves the user's input for editing.
- **Domain mismatch**: return `{ code: 'OFF_TOPIC', domain, suggestion }`. Frontend shows scope explanation with example queries.

Never use the same generic "I can't help with that" for both cases.

## Prompt Injection Defense

Treat prompt injection as part of the safety taxonomy (System Security domain), not a separate system:

- Include jailbreak samples from WildGuardMix in training data
- Regex pre-filter for known injection patterns (DAN, "ignore previous instructions", etc.)
- Never pass system prompts or internal instructions in the user-visible context window
- Consider WildGuard (7B) if adversarial attempts are frequent

## kyno Current State

No moderation exists. `convex/chat.ts` `sendMessage` sends raw user input directly to Groq. Integration points:

- **Server-side filter**: middleware in `sendMessage` before `fetch(GROQ_CHAT_URL, ...)`
- **Frontend blocked state**: `src/views/ChatView.vue` — edit-and-retry UX
- **Frontend response handling**: `src/composables/useGroqChat.ts` — handle new response codes
