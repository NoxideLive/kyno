#!/usr/bin/env bash
# Install NVIDIA Container Toolkit on Ubuntu (enables `docker run --gpus all`).
# Requires: NVIDIA driver on host (`nvidia-smi` works), Docker Engine (not snap).
#
# Usage:
#   sudo ./scripts/install-nvidia-container-toolkit.sh   # system packages + CDI spec
#   ./scripts/install-nvidia-container-toolkit.sh --rootless   # rootless Docker (no sudo)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rootless_setup() {
  if ! docker info 2>/dev/null | grep -q 'rootless: true'; then
    echo "Rootless Docker not detected — skipping user daemon setup." >&2
    return 0
  fi

  echo "Configuring rootless Docker for GPU (CDI)..."
  mkdir -p "${HOME}/.config/docker" "${HOME}/.docker/run/cdi"

  if [[ -f /etc/cdi/nvidia.yaml ]]; then
    cp /etc/cdi/nvidia.yaml "${HOME}/.docker/run/cdi/nvidia.yaml"
  else
    echo "ERROR: /etc/cdi/nvidia.yaml missing. Run the sudo install step first." >&2
    exit 1
  fi

  nvidia-ctk runtime configure --runtime=docker --cdi.enabled --config="${HOME}/.config/docker/daemon.json"

  if [[ -f /etc/nvidia-container-runtime/config.toml ]]; then
    if sudo -n nvidia-ctk config --set nvidia-container-cli.no-cgroups --in-place 2>/dev/null; then
      echo "Set nvidia-container-cli.no-cgroups for rootless."
    else
      echo "Optional (rootless): sudo nvidia-ctk config --set nvidia-container-cli.no-cgroups --in-place"
    fi
  fi

  systemctl --user restart docker
  sleep 2

  echo "Testing GPU in rootless Docker..."
  docker run --rm --gpus all pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime nvidia-smi

  echo ""
  echo "Rootless GPU setup done. Start phi-gateway with:"
  echo "  cd ${ROOT}"
  echo "  docker compose --env-file .env.local --profile dev up -d phi-gateway"
}

system_install() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run with sudo: sudo ./scripts/install-nvidia-container-toolkit.sh" >&2
    exit 1
  fi

  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "ERROR: nvidia-smi not found. Install NVIDIA drivers first." >&2
    exit 1
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not found." >&2
    exit 1
  fi

  echo "Adding NVIDIA Container Toolkit repository..."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list

  apt-get update
  apt-get install -y nvidia-container-toolkit

  echo "Configuring system Docker runtime..."
  nvidia-ctk runtime configure --runtime=docker

  echo "Generating CDI specs..."
  nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

  if systemctl is-active --quiet docker 2>/dev/null; then
    systemctl restart docker
  fi

  echo ""
  echo "System toolkit installed."
  if docker info 2>/dev/null | grep -q 'rootless: true'; then
    echo "Rootless Docker detected — run as your user:"
    echo "  ./scripts/install-nvidia-container-toolkit.sh --rootless"
  else
    echo "Testing GPU in Docker..."
    docker run --rm --gpus all pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime nvidia-smi
  fi
}

case "${1:-}" in
  --rootless) rootless_setup ;;
  *) system_install; rootless_setup 2>/dev/null || true ;;
esac
