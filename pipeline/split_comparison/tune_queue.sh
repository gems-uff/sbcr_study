#!/usr/bin/env bash
# Tunes SBCR for each dataset and arm (the grid on 100 training conflicts) in one global queue of
# five slots, the longest first. The search is bounded by wall-clock time, so the number of
# processes at once changes the result: five slots on 24 cores keeps the concurrency fixed.
#   ROOT=<root> pipeline/split_comparison/tune_queue.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sbcr-analysis
cd "$ROOT/sbcr"
export NUM_CHUNKS=100
SLOTS=5
queue=(
  "dataset2_Java random" "dataset2_Java mg" "dataset2_Java pd"
  "dataset1 random" "dataset1 mg" "dataset1 pd"
  "dataset2_CSharp random" "dataset2_CSharp mg" "dataset2_CSharp pd"
  "dataset2_JavaScript random" "dataset2_JavaScript mg" "dataset2_JavaScript pd"
  "dataset2_TypeScript random" "dataset2_TypeScript mg" "dataset2_TypeScript pd"
)
for item in "${queue[@]}"; do
  set -- $item; ds=$1; arm=$2
  while [ "$(pgrep -fc '[s]bcr_tuning\.py' || echo 0)" -ge "$SLOTS" ]; do sleep 60; done
  if [ "$ds" = "dataset1" ]; then target="dataset1_${arm}"; else target="${ds}_${arm}_combination"; fi
  label="${ds}_${arm}"
  echo "=== $label :: start $(date -Is) ==="
  ( python sbcr_tuning.py "$target" "tuning_${label}" > "../mergeGen/LOGS/tuning_${label}.log" 2>&1
    echo "=== $label :: end $(date -Is) ===" >> "../mergeGen/LOGS/tunings_queue.log" ) &
  sleep 5
done
wait
echo "=== tunings finished :: $(date -Is) ==="
