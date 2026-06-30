# Fine-Tuning Methods

Computationally cheap but accurate approaches for fine-tuning open-weight models on moderation and domain classification tasks.

## Recommended Approach: Cascaded Gateway

Rather than one model doing everything, use a two-tier system where each tier is optimized for its job.

### Tier 1: Fast-path binary filter (encoder)

**Model**: ModernBERT-base or DistilBERT

Classifies content as `safe` or `needs_review` in a single forward pass. No autoregressive generation — ~40–50x faster than decoders.

Handles the majority of traffic. Only uncertain cases escalate to Tier 2.

### Tier 2: Policy auditor (small LLM + classification head)

**Model**: Llama-3.2-1B/3B or Qwen2.5-7B

**Technique**: QDoRA with an embedding-based classification head.

Attach a linear layer to the final token's hidden state instead of prompting the LLM to generate a label. This matches BERT-class accuracy while leveraging LLM reasoning for edge cases.

## Parameter-Efficient Fine-Tuning (PEFT)

### QDoRA — recommended method

Quantized Weight-Decomposed Low-Rank Adaptation combines:

- **4-bit NF4 quantization** (QLoRA memory savings)
- **DoRA decomposition** (better learning stability than plain LoRA)

Configuration:

```
target_modules = "all-linear"   # capture behavioral nuances everywhere
rank (r) = 16 or 32             # sufficient for moderation
rsLoRA = true                   # if using rank 64+ to prevent gradient collapse
```

### Why not full fine-tuning?

Full fine-tuning of a 7B model requires 20–24 GB VRAM and risks catastrophic forgetting. QDoRA on 5,000 examples achieves comparable accuracy at ~$1–5 spot GPU cost.

### Why classification heads, not JSON generation?

Even small LLMs produce brittle free-form JSON. Parsing failures break the gateway. A linear classification head outputs logits directly — no parsing, no constrained decoding needed.

If you must use decoder-only generation, use [XGrammar](https://github.com/mlc-ai/xgrammar) or Outlines for constrained decoding.

## Data Requirements

### Quantity

1,000–5,000 high-quality, diverse examples outperform 50,000 noisy ones for classification tasks.

### Synthetic data generation

Use a frontier model (GPT-4o, Claude 3.5) as a teacher:

1. **Generate edge cases**: prompt the teacher with your policy taxonomy and ask for boundary examples.
2. **Active learning loop**: train the small model → find low-confidence predictions → generate more samples for those boundaries → retrain.
3. **Multi-agent debate**: use Advocate vs Judge agents to verify synthetic labels before adding to the training set.

Estimated cost: ~$2–10 for 5,000 samples via GPT-4o-mini.

### Labeling strategy

| Task | Label type | Example labels |
|------|-----------|----------------|
| Safety | Multi-label | `toxicity`, `pii`, `jailbreak`, `safe` |
| Domain | Single-label | `on_topic`, `off_topic`, `needs_clarification` |

Use multi-label for safety (a message can violate multiple policies). Use single-label for domain routing.

## Training Recipe

| Component | Value |
|-----------|-------|
| Base model | Llama-3.2-3B-Instruct or Qwen2.5-7B |
| Method | QDoRA (4-bit NF4 + DoRA) |
| Head | Sequence classification (linear on last token hidden state) |
| Learning rate | 2e-4 |
| Batch size | 32–64 |
| Epochs | 3 |
| Scheduler | Cosine with 10% warmup |
| Hardware | Single RTX 4090 (24GB) or A100 |

### Training time and cost

| Model size | Examples | Time (4090) | Spot GPU cost |
|-----------|----------|-------------|---------------|
| 1B | 3,000 | ~30 min | ~$0.50 |
| 3B | 3,000 | ~1–2 hours | ~$1–2 |
| 7B | 5,000 | ~2–4 hours | ~$2–5 |

Tools: [Unsloth](https://github.com/unslothai/unsloth) for fast 4-bit fine-tuning, [HuggingFace PEFT](https://huggingface.co/docs/peft) for adapter management.

## Distillation Path

Once Tier 2 (LLM) performs well:

1. Run Tier 2 on your evaluation set, collecting logits/probabilities.
2. Train Tier 1 (ModernBERT) to match Tier 2's outputs via knowledge distillation.
3. Deploy Tier 1 as the primary filter; Tier 2 handles only low-confidence cases.

This "shifts accuracy left" into the faster model, reducing average latency and cost.

## Evaluation Metrics

| Metric | Priority | Why |
|--------|----------|-----|
| Recall (harmful) | High | Missing unsafe content is worse than blocking safe content |
| Precision (safe) | High | False positives kill user engagement |
| F1 (per category) | Medium | Balance for multi-label safety |
| Latency p99 | High | Gateway must stay under 200ms |

Optimize thresholds per category: higher precision for harassment (avoid over-blocking), higher recall for legal risks (CSAM, threats).

## Pitfalls

- **Free-form JSON output**: brittle, slow, parsing failures. Use classification heads.
- **High false positive rate**: kills engagement. Tune thresholds on real user data, not just benchmarks.
- **Training on noisy data at scale**: 50k noisy labels < 3k curated labels for classification.
- **Ignoring adversarial examples**: include jailbreak and prompt injection samples from WildGuardMix in training data.
- **No output filtering**: input-only moderation misses LLM-generated harmful responses.

## References

- [DoRA: Weight-Decomposed Low-Rank Adaptation](https://arxiv.org/abs/2402.09353) (Liu et al., 2024)
- [HuggingFace PEFT Documentation](https://huggingface.co/docs/peft)
- [Unsloth: Fast 4-bit Fine-Tuning](https://github.com/unslothai/unsloth)
- [XGrammar: Structured Generation Engine](https://github.com/mlc-ai/xgrammar)

## Summary

Fine-tune Llama-3.2-3B with QDoRA and a classification head on ~3,000 synthetic examples. Distill into ModernBERT for production. Total cost: ~$5–15 for data generation + training.
