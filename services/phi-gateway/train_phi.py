#!/usr/bin/env python3
"""Fine-tune Phi-4-mini-instruct for CAPS Mathematics domain classification.

GPU-only. Exits if CUDA is unavailable.

Use --low-vram on 4 GB cards: prepares the model on CPU, then trains with a
CPU/GPU split (slower, much less VRAM). Auto-enabled when total VRAM < 6 GiB.

Example:
  python services/phi-gateway/train_phi.py
  python services/phi-gateway/train_phi.py --low-vram
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from accelerate import dispatch_model, infer_auto_device_map
from accelerate.utils import get_balanced_memory
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer

from phi_config import (
    DOMAIN_SYSTEM_PROMPT,
    LORA_CONFIG,
    PHI_ADAPTER_DIR,
    PHI_MODEL_ID,
    TRAINING_CONFIG,
)

ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = ROOT / "training" / "domain"
LOW_VRAM_GPU_BUDGET = "3400MiB"
LOW_VRAM_CPU_BUDGET = "48GiB"
PHI_DECODER_LAYER = "Phi3DecoderLayer"


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def to_chat_dataset(rows: list[dict]) -> Dataset:
    messages_list = []
    for row in rows:
        messages_list.append(
            {
                "messages": [
                    {"role": "system", "content": DOMAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": row["text"]},
                    {"role": "assistant", "content": row["label"]},
                ]
            }
        )
    return Dataset.from_list(messages_list)


def apply_chat_template(example: dict, tokenizer) -> dict:
    example["text"] = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return example


def require_gpu() -> None:
    if not torch.cuda.is_available():
        print("CUDA GPU required. Training aborted.", file=sys.stderr)
        raise SystemExit(1)

    name = torch.cuda.get_device_name(0)
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    free_gib = free_bytes / (1024**3)
    total_gib = total_bytes / (1024**3)
    print(f"GPU: {name} ({free_gib:.1f} GiB free / {total_gib:.1f} GiB total)")
    if free_gib < 1.0:
        print("Insufficient free VRAM. Training aborted.", file=sys.stderr)
        raise SystemExit(1)


def require_gpu() -> float:
    if not torch.cuda.is_available():
        print("CUDA GPU required. Training aborted.", file=sys.stderr)
        raise SystemExit(1)

    name = torch.cuda.get_device_name(0)
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    free_gib = free_bytes / (1024**3)
    total_gib = total_bytes / (1024**3)
    print(f"GPU: {name} ({free_gib:.1f} GiB free / {total_gib:.1f} GiB total)")
    if free_gib < 1.0:
        print("Insufficient free VRAM. Training aborted.", file=sys.stderr)
        raise SystemExit(1)
    return total_gib


def load_model_for_training(
    bnb_config: BitsAndBytesConfig,
    peft_conf: LoraConfig,
    *,
    low_vram: bool,
) -> torch.nn.Module:
    gc_kwargs = TRAINING_CONFIG["gradient_checkpointing_kwargs"]

    if low_vram:
        print("Low-VRAM mode: preparing on CPU, then dispatching layers to GPU (slower).")
        model = AutoModelForCausalLM.from_pretrained(
            PHI_MODEL_ID,
            quantization_config=bnb_config,
            trust_remote_code=True,
            device_map="cpu",
            low_cpu_mem_usage=True,
        )
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs=gc_kwargs,
        )
        model = get_peft_model(model, peft_conf)
        max_memory = get_balanced_memory(
            model,
            max_memory={0: LOW_VRAM_GPU_BUDGET, "cpu": LOW_VRAM_CPU_BUDGET},
        )
        device_map = infer_auto_device_map(
            model,
            max_memory=max_memory,
            no_split_module_classes=[PHI_DECODER_LAYER],
        )
        return dispatch_model(model, device_map=device_map)

    model = AutoModelForCausalLM.from_pretrained(
        PHI_MODEL_ID,
        quantization_config=bnb_config,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    torch.cuda.empty_cache()
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs=gc_kwargs,
    )
    return get_peft_model(model, peft_conf)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-dir", type=Path, default=TRAINING_DIR)
    parser.add_argument("--output-dir", type=Path, default=PHI_ADAPTER_DIR)
    parser.add_argument(
        "--low-vram",
        action="store_true",
        help="CPU prep + CPU/GPU layer split for 4 GB GPUs (slower)",
    )
    parser.add_argument(
        "--no-auto-low-vram",
        action="store_true",
        help="Do not auto-enable low-VRAM mode on GPUs under 6 GiB",
    )
    args = parser.parse_args()

    total_gib = require_gpu()
    low_vram = args.low_vram or (not args.no_auto_low_vram and total_gib < 6.0)
    if low_vram and not args.low_vram:
        print(f"Auto-enabled low-VRAM mode ({total_gib:.1f} GiB GPU).")

    train_path = args.training_dir / "train.jsonl"
    val_path = args.training_dir / "val.jsonl"
    if not train_path.is_file():
        print(f"Missing {train_path}. Run scripts/generate_domain_training_data.py first.", file=sys.stderr)
        return 1

    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path) if val_path.is_file() else []

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    peft_conf = LoraConfig(**LORA_CONFIG)

    try:
        model = load_model_for_training(bnb_config, peft_conf, low_vram=low_vram)
    except torch.cuda.OutOfMemoryError:
        if low_vram:
            print("CUDA OOM during model setup. Training aborted.", file=sys.stderr)
        else:
            print(
                "CUDA OOM during model setup. Retry with --low-vram (4 GB GPUs).",
                file=sys.stderr,
            )
        raise SystemExit(1) from None

    tokenizer = AutoTokenizer.from_pretrained(PHI_MODEL_ID, trust_remote_code=True)
    tokenizer.model_max_length = TRAINING_CONFIG["max_seq_length"]
    tokenizer.pad_token = tokenizer.unk_token
    tokenizer.pad_token_id = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)
    tokenizer.padding_side = "right"

    train_dataset = to_chat_dataset(train_rows)
    eval_dataset = to_chat_dataset(val_rows) if val_rows else None

    train_dataset = train_dataset.map(
        apply_chat_template,
        fn_kwargs={"tokenizer": tokenizer},
        remove_columns=train_dataset.column_names,
    )
    if eval_dataset is not None:
        eval_dataset = eval_dataset.map(
            apply_chat_template,
            fn_kwargs={"tokenizer": tokenizer},
            remove_columns=eval_dataset.column_names,
        )

    training_args = SFTConfig(
        output_dir=str(args.output_dir),
        bf16=TRAINING_CONFIG["bf16"],
        learning_rate=TRAINING_CONFIG["learning_rate"],
        logging_steps=TRAINING_CONFIG["logging_steps"],
        lr_scheduler_type=TRAINING_CONFIG["lr_scheduler_type"],
        num_train_epochs=TRAINING_CONFIG["num_train_epochs"],
        per_device_train_batch_size=TRAINING_CONFIG["per_device_train_batch_size"],
        gradient_accumulation_steps=TRAINING_CONFIG["gradient_accumulation_steps"],
        gradient_checkpointing=TRAINING_CONFIG["gradient_checkpointing"],
        gradient_checkpointing_kwargs=TRAINING_CONFIG["gradient_checkpointing_kwargs"],
        warmup_ratio=TRAINING_CONFIG["warmup_ratio"],
        save_total_limit=TRAINING_CONFIG["save_total_limit"],
        report_to="none",
        eval_strategy="no",
        max_seq_length=TRAINING_CONFIG["max_seq_length"],
        dataset_text_field="text",
        packing=False,
        use_cpu=False,
        optim="paged_adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"Phi domain LoRA saved → {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
