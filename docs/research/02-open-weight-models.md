# Open-Weight Model Selection

Comparison of open-weight task-agnostic models suitable for moderation gateway and domain classification tasks in kyno.

## Model Comparison

| Model | Size | License | Moderation | Inference (Q4) | Strength |
|-------|------|---------|------------|-----------------|----------|
| **Qwen3-Guard** | 4B | Apache 2.0 | High (multilingual) | ~3 GB VRAM | Best recall, 119 languages |
| **Llama Guard 3** | 1B / 8B | Llama Comm. | High (general) | ~1.5–5 GB VRAM | Standard English safety |
| **ModernBERT** | 149M | Apache 2.0 | Medium (pattern) | <1 GB VRAM | Ultra-low latency classification |
| **SmolLM3** | 1.7B / 3B | Apache 2.0 | Medium (tunable) | ~1.5–2.5 GB VRAM | Fully open recipe |
| **Phi-4-mini** | 3.8B | MIT | Medium (reasoning) | ~2.8 GB VRAM | High reasoning density |
| **ShieldGemma** | 2B | Gemma Terms | Medium (precision) | ~2 GB VRAM | Low false positives |
| **WildGuard** | 7B | Apache 2.0 | High (adversarial) | ~5 GB VRAM | Jailbreak robustness (+25% vs Llama Guard) |

## Top Recommendations

### 1. Qwen3-Guard (4B) — primary safety layer (multilingual)

Best overall recall across safety benchmarks. Apache 2.0 license with no commercial restrictions.

- HuggingFace: [Qwen/Qwen3-Guard-4B](https://huggingface.co/Qwen/Qwen3-Guard-4B)
- Use when: multilingual support needed, or highest recall is priority

### 2. Llama Guard 3 (1B) — primary safety layer (English, low cost)

Standard choice for English-only moderation. Smallest viable guard model.

- HuggingFace: [meta-llama/Llama-Guard-3-1B](https://huggingface.co/meta-llama/Llama-Guard-3-1B)
- Use when: English-only, latency and cost are primary constraints

### 3. ModernBERT-base — domain/intent classifier

Encoder model, ~40–50x faster than decoders for classification. Best for high-volume domain routing.

- HuggingFace: [answerdotai/ModernBERT-base](https://huggingface.co/answerdotai/ModernBERT-base)
- Use when: fixed label set (on-topic / off-topic), sub-10ms latency required

### 4. Llama-3.2-1B-Instruct — micro domain classifier

High plasticity for fine-tuning on specific domain labels. Better than encoders when classification requires contextual reasoning.

- HuggingFace: [meta-llama/Llama-3.2-1B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct)
- Use when: domain boundaries are nuanced, zero-shot flexibility needed

### 5. WildGuard (7B) — adversarial defense

Specialized for jailbreak and prompt injection detection. Outperforms Llama Guard by up to 25% on adversarial benchmarks.

- HuggingFace: [allenai/wildguard](https://huggingface.co/allenai/wildguard)
- Use when: facing frequent jailbreak attempts

### 6. SmolLM3-3B — commercial redistribution base

Apache 2.0 with fully open training recipe. Avoids Llama MAU caps and Gemma use restrictions.

- HuggingFace: [HuggingFaceTB/SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B)
- Use when: redistributing a fine-tuned model to customers

## Encoder vs Decoder vs Guard

| Type | Best for | Latency | Flexibility |
|------|----------|---------|-------------|
| **Encoder** (ModernBERT, DeBERTa) | Fixed-label classification, domain routing | <10ms | Low (fixed labels) |
| **Small LLM** (Llama 1B, Qwen 1.7B) | Reasoning-heavy classification, zero-shot | 50–100ms | Medium |
| **Guard model** (Llama Guard, Qwen Guard) | Safety taxonomy, pre-trained harms | 50–100ms | Medium (safety labels) |

**Recommendation for kyno**: Guard model for safety (Tier 1), ModernBERT for domain routing (Tier 2). Add a small LLM only if domain boundaries require reasoning.

## Hardware Requirements

| Task | 1B | 3–4B | 7–8B |
|------|----|----|------|
| Inference (4-bit) | ~1.5 GB | ~3 GB | ~5 GB |
| QLoRA fine-tune | ~4 GB | ~8 GB | ~12–14 GB |
| LoRA fine-tune | ~6 GB | ~12 GB | ~20–24 GB |

**Consumer setup**: RTX 4070 (12GB) or 4060 Ti (16GB) handles QLoRA fine-tuning up to 8B.

**Production inference**: CPU inference via `llama.cpp` works but a small GPU (T4, L4) keeps latency under 100ms.

## Licensing for Commercial Use

| License | Models | Notes |
|---------|--------|-------|
| Apache 2.0 / MIT | Qwen, SmolLM, Phi, WildGuard | No restrictions. Best for SaaS. |
| Llama Community | Llama Guard, Llama 3.x | Free up to 700M MAU. Requires attribution. |
| Gemma Terms | ShieldGemma | Allowed but subject to Google Prohibited Use Policy. |

For kyno as a commercial product, prefer Apache 2.0 models (Qwen3-Guard, ModernBERT, SmolLM3) to avoid license complexity.

## Recommended kyno Stack

| Role | Model | Why |
|------|-------|-----|
| Safety gate | Llama Guard 3 (1B) | Cheapest viable guard, English chat |
| Domain router | ModernBERT-base (fine-tuned) | Sub-10ms, fixed on/off-topic labels |
| Custom policy (later) | Llama-3.2-3B + QDoRA | When guard models miss domain-specific rules |
| Adversarial defense (if needed) | WildGuard (7B) | Jailbreak-heavy environments |
