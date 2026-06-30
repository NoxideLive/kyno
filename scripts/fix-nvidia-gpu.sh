#!/usr/bin/env bash
# Fix NVIDIA driver when nvidia-smi fails after a kernel update.
# Root cause: kernel modules installed for an older kernel than the one running.
set -euo pipefail

KERNEL="$(uname -r)"
echo "Running kernel: ${KERNEL}"

if ! lspci | grep -qi nvidia; then
  echo "No NVIDIA GPU found on PCI bus."
  exit 1
fi

echo "Installing NVIDIA kernel modules for ${KERNEL}..."
sudo apt-get update
sudo apt-get install -y \
  "linux-modules-nvidia-580-open-${KERNEL}" \
  linux-modules-nvidia-580-open-generic-hwe-24.04 \
  nvidia-driver-580-open

echo "Loading nvidia module..."
sudo modprobe nvidia || true

if nvidia-smi; then
  echo "GPU OK."
  exit 0
fi

echo ""
echo "nvidia-smi still failing. Common causes:"
echo "  1. Reboot required:  sudo reboot"
echo "  2. Secure Boot (enabled on this machine) — enroll NVIDIA MOK after driver install"
echo "  3. Newer GPU — try recommended driver:"
echo "       sudo apt install nvidia-driver-595-open"
echo "       sudo reboot"
exit 1
