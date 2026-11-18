#!/usr/bin/env bash
# Trains one MergeGen model per dataset and arm, with the original configuration (CodeT5-small,
# 500/200, batch 35), in series on one GPU, waiting for 20 GB of free memory before each training.
#   ROOT=<root> pipeline/split_comparison/train.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
cd "$ROOT/mergeGen"
mkdir -p LOGS
NEEDED_MIB=${NEEDED_MIB:-20000}
wait_gpu() {
  local free
  while true; do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    if [ "$free" -ge "$NEEDED_MIB" ]; then return 0; fi
    echo "$(date -Is) waiting for the GPU: ${free} MiB free, need ${NEEDED_MIB} MiB"
    sleep 300
  done
}
for arm in random mg pd; do
  for d in dataset1 dataset2_Java dataset2_CSharp dataset2_JavaScript dataset2_TypeScript; do
    name="${d}_${arm}"
    if [ -f "MODELS/${name}/best_model.pt" ]; then
      echo "=== $name :: already trained, skipping ==="
      continue
    fi
    wait_gpu
    echo "=== $name :: start $(date -Is) ==="
    /usr/bin/time -o "LOGS/${name}_train_time.txt" -f "%E" \
      python run_mergegen.py "$name" train > "LOGS/${name}_train.log" 2>&1
    echo "=== $name :: end $(date -Is) :: $(cat LOGS/${name}_train_time.txt 2>/dev/null) ==="
  done
done
echo "=== campaign finished :: $(date -Is) ==="
