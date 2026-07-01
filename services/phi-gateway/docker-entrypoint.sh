#!/usr/bin/env bash
set -euo pipefail

echo "Checking CUDA availability..."
python - <<'PY'
import sys
import torch

if not torch.cuda.is_available():
    print("ERROR: CUDA is not available inside the container.", file=sys.stderr)
    print("Install NVIDIA Container Toolkit and run with GPU access (compose: gpus: all).", file=sys.stderr)
    sys.exit(1)

device = torch.cuda.get_device_name(0)
mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
print(f"CUDA OK: {device} ({mem_gb:.1f} GiB)")
PY

exec uvicorn server:app --host 0.0.0.0 --port 8090
