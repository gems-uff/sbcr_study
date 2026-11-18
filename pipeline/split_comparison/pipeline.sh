#!/usr/bin/env bash
# Waits for the tokenization, links its blocks to the three arms and trains.
#   ROOT=<root> pipeline/split_comparison/pipeline.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mergegen-train
while pgrep -f "run_total_dataset.py" > /dev/null || pgrep -f "dataset_parallel.py" > /dev/null; do sleep 30; done
echo "=== tokenization finished :: $(date -Is) ==="
python "$REPO/preparation/prepare_data.py" --root "$ROOT" --links
"$REPO/pipeline/split_comparison/train.sh"
