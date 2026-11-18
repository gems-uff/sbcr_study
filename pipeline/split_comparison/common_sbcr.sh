#!/usr/bin/env bash
# SBCR on the test partition of the pd arm with the configurations of the random and mg arms, seed
# 3022024, so that the three arms are compared on the same conflicts on SBCR's side too.
#   ROOT=<root> pipeline/split_comparison/common_sbcr.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sbcr-analysis
cd "$ROOT/sbcr"
SLOTS=5
wait_slot() { while [ "$(pgrep -fc '[s]bcr_evaluate\.py' || echo 0)" -ge "$SLOTS" ]; do sleep 60; done; }

config() {  # $1=dataset $2=arm -> selected configuration
  python - "$1" "$2" <<'PY'
import pandas as pd, sys, os
t = pd.read_csv(os.path.join(os.environ["ROOT"], "selected_configurations.csv"))
print(t[t.run == f"{sys.argv[1]}_{sys.argv[2]}"].configuration.iloc[0].replace(" ", ""))
PY
}

for arm in random mg; do
  for item in "dataset1 dataset1 dataset1_pd" "dataset2_Java dataset2_Java dataset2_Java_pd_combination" \
              "dataset2_CSharp dataset2_CSharp dataset2_CSharp_pd_combination" \
              "dataset2_JavaScript dataset2_JavaScript dataset2_JavaScript_pd_combination" \
              "dataset2_TypeScript dataset2_TypeScript dataset2_TypeScript_pd_combination" \
              "rq3_ds1 dataset2_Java dataset1_pd" "rq3_java dataset1 dataset2_Java_pd_combination"; do
    set -- $item; tag=$1; source=$2; target=$3
    cfg=$(config "$source" "$arm")
    wait_slot
    echo "=== common_${tag}_${arm} ($cfg) :: start $(date -Is) ==="
    ( SEED=3022024 python sbcr_evaluate.py "$target" "$cfg" "eval_common_${tag}_${arm}" \
        > "../mergeGen/LOGS/eval_common_${tag}_${arm}.log" 2>&1 ) &
    sleep 3
  done
done
wait
echo "=== SBCR common set finished :: $(date -Is) ==="
