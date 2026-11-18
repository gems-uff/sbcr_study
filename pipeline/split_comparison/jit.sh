#!/usr/bin/env bash
# Generates MergeGen's candidates and times each step of every test conflict, in the three arms.
#   ROOT=<root> pipeline/split_comparison/jit.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mergegen-train
for arm in random mg pd; do
  echo "=== arm $arm :: start $(date -Is) ==="
  python "$REPO/mergegen/jit_inference.py" --root "$ROOT" --arm $arm
  echo "=== arm $arm :: end $(date -Is) ==="
done
echo "=== just-in-time inference finished :: $(date -Is) ==="
