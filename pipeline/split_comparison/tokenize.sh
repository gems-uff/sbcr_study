#!/usr/bin/env bash
# Tokenizes each dataset once; the slices of each arm come from the first run_mergegen.py of the arm.
#   ROOT=<root> pipeline/split_comparison/tokenize.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -euo pipefail
cd "$ROOT/mergeGen"
for d in dataset1 dataset2_Java dataset2_CSharp dataset2_JavaScript dataset2_TypeScript; do
  echo "=== $d :: $(date -Is) ==="
  python run_total_dataset.py "$d" dataset_parallel.py
done
echo "=== end :: $(date -Is) ==="
