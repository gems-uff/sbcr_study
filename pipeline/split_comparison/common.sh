#!/usr/bin/env bash
# Runs the models of the random and mg arms on the test partition of pd, so that the three arms are
# compared on the same conflicts.
#   ROOT=<root> pipeline/split_comparison/common.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mergegen-train
for arm in random mg; do
  echo "=== $arm model on the pd test :: start $(date -Is) ==="
  python "$REPO/mergegen/jit_inference.py" --root "$ROOT" --arm $arm --test-of pd
  echo "=== $arm model on the pd test :: end $(date -Is) ==="
done
echo "=== common set finished :: $(date -Is) ==="
