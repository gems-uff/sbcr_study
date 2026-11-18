#!/usr/bin/env bash
# Prepares one partition of the merge-grouped design: the split with the draw seed and the rule,
# the acceptance test (contamination, concentration and sizes), the data, the tokenization, the
# cut references and the partitions SBCR reads. Only the `mg` arm, and optionally the `pd` arm of
# another root, for the common set.
#
# Idempotent: each step writes a marker in $ROOT/markers when it ends, and is skipped if the marker
# exists. A step that was interrupted is redone from scratch.
#
#   ROOT=<new root> DRAW_SEED=<seed> DATA_ROOT=<datasets/source> BACKBONES=<dir> pipeline/prepare_partition.sh
#
# Optional variables:
#   TRAINING_SEED  MergeGen's training seed; default, the draw seed
#   RULE           largest-first (default) or cap
#   CAP            with RULE=cap, the largest share of the test a group may take (0.05)
#   TOLERANCE      relative deviation accepted in the evaluated test; 0 requires TARGET exactly
#   PD_FROM        root to copy the `pd` partitions from, for the common set
REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOT="${ROOT:?set ROOT, the root of the partition}"
DRAW_SEED="${DRAW_SEED:?set DRAW_SEED}"
DATA_ROOT="${DATA_ROOT:?set DATA_ROOT, the folder of the two datasets}"
BACKBONES="${BACKBONES:?set BACKBONES, the folder with codet5-small-local}"
TRAINING_SEED="${TRAINING_SEED:-$DRAW_SEED}"
RULE="${RULE:-largest-first}"
CAP="${CAP:-0.05}"
TOLERANCE="${TOLERANCE:-0}"
PD_FROM="${PD_FROM:-}"
export REPO ROOT
set -euo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
mkdir -p "$ROOT/markers" "$ROOT/logs"
M="$ROOT/markers"

# Parameters written in the root; running again with others is an error, not a resumption.
fix() {  # $1 = file, $2 = value
  if [ -f "$ROOT/$1" ]; then
    [ "$(cat "$ROOT/$1")" = "$2" ] || { echo "ERROR: $ROOT/$1 holds $(cat "$ROOT/$1"), not $2"; exit 1; }
  else
    echo "$2" > "$ROOT/$1"
  fi
}
fix draw_seed.txt "$DRAW_SEED"
fix training_seed.txt "$TRAINING_SEED"
fix rule.txt "$RULE$([ "$RULE" = cap ] && echo " $CAP")"

ARMS=mg
[ -n "$PD_FROM" ] && ARMS=mg,pd

step() { echo "=== $1 :: $(date -Is) ==="; }

conda activate sbcr-analise

if [ ! -f "$M/splits.ok" ]; then
  step "splits (seed $DRAW_SEED, rule $RULE)"
  rm -rf "$ROOT/splits/mg"
  python "$REPO/preparation/make_splits.py" --data-root "$DATA_ROOT" --out "$ROOT/splits" \
    --seed "$DRAW_SEED" --arms mg --rule "$RULE" --cap "$CAP" > "$ROOT/logs/splits.log" 2>&1
  touch "$M/splits.ok"
fi

if [ -n "$PD_FROM" ] && [ ! -f "$M/pd_copied.ok" ]; then
  step "pd partitions copied from $PD_FROM"
  mkdir -p "$ROOT/splits/pd"
  cp "$PD_FROM"/splits/pd/*.csv "$ROOT/splits/pd/"
  touch "$M/pd_copied.ok"
fi

if [ ! -f "$M/acceptance.ok" ]; then
  step "acceptance test: contamination and concentration"
  python - "$ROOT/splits" "$RULE" "$CAP" "$TOLERANCE" <<'PY'
import sys, pandas as pd
d, rule, cap, tol = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
check = pd.read_csv(f"{d}/acceptance_check.csv")
summary = pd.read_csv(f"{d}/summary.csv").set_index("dataset")
print(check.to_string(index=False))
print(summary[["train", "validation", "test", "largest_group", "largest_group_test", "pct_largest_group_test"]].to_string())
failures = []
if (check.twin != 0).any() or (check["merge"] != 0).any():
    failures.append("contamination by an exact twin or by a merge")
if rule == "cap" and (summary.pct_largest_group_test > 100 * cap).any():
    failures.append(f"group above the cap of {cap:.0%} in the test")
if tol == 0:
    expected = {  # dataset: (train, validation, test) of the largest-first rule
        "dataset1": (4392, 549, 549), "dataset2_Java": (46103, 5763, 5762),
        "dataset2_CSharp": (13052, 1632, 1632), "dataset2_JavaScript": (37501, 4688, 4688),
        "dataset2_TypeScript": (9208, 1152, 1151)}
    for ds, size in expected.items():
        got = tuple(int(summary.loc[ds, c]) for c in ("train", "validation", "test"))
        if got != size:
            failures.append(f"{ds}: sizes {got}, expected {size}")
if failures:
    print("ACCEPTANCE FAILED:\n  " + "\n  ".join(failures)); sys.exit(1)
print("acceptance: ok")
PY
  touch "$M/acceptance.ok"
fi

if [ ! -f "$M/data.ok" ]; then
  step "data"
  python "$REPO/preparation/prepare_data.py" --data-root "$DATA_ROOT" --root "$ROOT" --backbones "$BACKBONES" \
    --arms "$ARMS" > "$ROOT/logs/data.log" 2>&1
  touch "$M/data.ok"
fi

conda activate mergegen-train
cd "$ROOT/mergeGen"
for d in dataset1 dataset2_Java dataset2_CSharp dataset2_JavaScript dataset2_TypeScript; do
  if [ ! -f "$M/tokenization_$d.ok" ]; then
    step "tokenization $d"
    rm -rf "PROCESSED/$d" "GIT_MERGE_FILES/$d"
    mkdir -p "PROCESSED/$d"
    python run_total_dataset.py "$d" dataset_parallel.py > "$ROOT/logs/tokenization_$d.log" 2>&1
    # run_total_dataset.py does not pass on a failure of its children, so the blocks are counted
    python - "$d" <<'PY'
import json, math, os, sys
d = sys.argv[1]
n = len(json.load(open(f"../data/{d}.json"))["chunk_id"])
missing = [f"processed_{i*1000}_{min((i+1)*1000, n)}.pkl" for i in range(math.ceil(n / 1000))
           if not os.path.exists(f"PROCESSED/{d}/processed_{i*1000}_{min((i+1)*1000, n)}.pkl")]
if missing:
    print(f"{d}: {len(missing)} blocks missing, the first {missing[0]}"); sys.exit(1)
print(f"{d}: {math.ceil(n/1000)} blocks")
PY
    touch "$M/tokenization_$d.ok"
  fi
done
cd "$ROOT"

if [ ! -f "$M/links.ok" ]; then
  step "tokenization links"
  python "$REPO/preparation/prepare_data.py" --root "$ROOT" --links --arms "$ARMS" >> "$ROOT/logs/data.log" 2>&1
  touch "$M/links.ok"
fi

if [ ! -f "$M/references.ok" ]; then
  step "truncated references"
  python "$REPO/preparation/truncated_references.py" --root "$ROOT" > "$ROOT/logs/references.log" 2>&1
  touch "$M/references.ok"
fi

conda activate sbcr-analise
if [ ! -f "$M/sbcr.ok" ]; then
  step "SBCR slices and acceptance of the evaluated test"
  mkdir -p "$ROOT/sbcr"
  cp "$REPO/sbcr/sbcr_evaluate.py" "$REPO/sbcr/sbcr_tuning.py" "$ROOT/sbcr/"
  python "$REPO/preparation/prepare_sbcr.py" --root "$ROOT" --arms "$ARMS" > "$ROOT/logs/sbcr_slices.log" 2>&1
  cat "$ROOT/logs/sbcr_slices.log"
  # the evaluated test (the combination subset) must be within the tolerance of TARGET
  python - "$ROOT/data" "$TOLERANCE" <<'PY'
import json, sys
d, tol = sys.argv[1], float(sys.argv[2])
target = {"dataset1_mg": 549, "dataset2_Java_mg_combination": 1717, "dataset2_CSharp_mg_combination": 546,
          "dataset2_JavaScript_mg_combination": 1207, "dataset2_TypeScript_mg_combination": 392}
failures = []
for label, n in target.items():
    got = len(json.load(open(f"{d}/{label}_testing.json"))["chunk_id"])
    deviation = (got - n) / n
    print(f"  {label}: {got} (target {n}, deviation {deviation:+.1%})")
    if abs(deviation) > tol + 1e-12:
        failures.append(label)
if failures:
    print(f"ACCEPTANCE FAILED: evaluated test outside the tolerance of {tol:.0%} in {failures}"); sys.exit(1)
print("acceptance of the evaluated test: ok")
PY
  touch "$M/sbcr.ok"
fi

step "preparation finished"
