#!/usr/bin/env bash
# Evaluates SBCR on the test partitions of the three arms with five seeds, after the tunings: applies
# the selection rule and uses the configurations it selects. The two crossed evaluations of RQ3 swap
# the configurations of Dataset1 and Dataset2_Java. Five slots, as in the tuning. Evaluations that did
# not finish are resumed with sbcr/resume_evaluations.py.
#   ROOT=<root> pipeline/split_comparison/evaluate.sh
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the three arms}"
export REPO ROOT
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sbcr-analise

while pgrep -f "[s]bcr_tuning\.py" > /dev/null; do sleep 300; done
echo "=== tunings finished, applying the selection rule :: $(date -Is) ==="
python "$REPO/sbcr/select_configuration.py" --root "$ROOT" | tail -25

cd "$ROOT/sbcr"
SLOTS=5
SEEDS="3022024 20260904 7412 98765 31337"

config() {  # $1=dataset $2=arm -> selected configuration
  python - "$1" "$2" <<'PY'
import pandas as pd, sys, os
t = pd.read_csv(os.path.join(os.environ["ROOT"], "selected_configurations.csv"))
row = t[t.run == f"{sys.argv[1]}_{sys.argv[2]}"]
print(row.configuration.iloc[0].replace(" ", ""))
PY
}

for arm in random mg pd; do
  cfg_ds1=$(config dataset1 $arm)
  cfg_java=$(config dataset2_Java $arm)
  for seed in $SEEDS; do
    for ds in dataset1 dataset2_Java dataset2_CSharp dataset2_JavaScript dataset2_TypeScript; do
      cfg=$(config $ds $arm)
      if [ "$ds" = "dataset1" ]; then target="dataset1_${arm}"; else target="${ds}_${arm}_combination"; fi
      while [ "$(pgrep -fc '[s]bcr_evaluate\.py' || echo 0)" -ge "$SLOTS" ]; do sleep 60; done
      label="${ds}_${arm}_s${seed}"
      echo "=== $label ($cfg) :: start $(date -Is) ==="
      ( SEED=$seed python sbcr_evaluate.py "$target" "$cfg" "eval_${label}" \
          > "../mergeGen/LOGS/eval_${label}.log" 2>&1 ) &
      sleep 3
    done
    # RQ3: the configurations swapped between Dataset1 and Dataset2_Java
    for pair in "dataset1 $cfg_java rq3_ds1" "dataset2_Java $cfg_ds1 rq3_java"; do
      set -- $pair; ds=$1; cfg=$2; tag=$3
      if [ "$ds" = "dataset1" ]; then target="dataset1_${arm}"; else target="${ds}_${arm}_combination"; fi
      while [ "$(pgrep -fc '[s]bcr_evaluate\.py' || echo 0)" -ge "$SLOTS" ]; do sleep 60; done
      label="${tag}_${arm}_s${seed}"
      echo "=== $label ($cfg) :: start $(date -Is) ==="
      ( SEED=$seed python sbcr_evaluate.py "$target" "$cfg" "eval_${label}" \
          > "../mergeGen/LOGS/eval_${label}.log" 2>&1 ) &
      sleep 3
    done
  done
done
wait
echo "=== SBCR evaluation finished :: $(date -Is) ==="
