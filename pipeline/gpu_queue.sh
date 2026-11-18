#!/usr/bin/env bash
# GPU queue of the merge-grouped partitions: training of the five MergeGen models and the
# just-in-time inference, one root after the other, all in series, since the GPU is shared and two
# trainings do not fit together. The training seed is $ROOT/training_seed.txt, passed to
# run_mergegen.py as TRAINING_SEED. If the root has the `pd` partitions (PD_FROM in the preparation),
# it also runs the model of `mg` on the test of `pd`, for the common set.
#
# Idempotent. A model counts as trained only with the marker markers/training_<name>.ok, written
# when the process ends well and train_process records the final time: best_model.pt alone does not
# count, since it is written at every improvement and run_mergegen.py would resume from it with the
# epoch counter and the learning rate reset. A training without the marker is deleted and redone.
#
#   ROOTS="<root 2> <root 3>" pipeline/gpu_queue.sh
REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOTS="${ROOTS:?set ROOTS, the roots of the partitions, space-separated}"
export REPO
set -uo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mergegen-train

# one instance of the queue at a time
first=${ROOTS%% *}
exec 9>"$first/markers/gpu.lock"
flock -n 9 || { echo "another instance of the GPU queue is running"; exit 1; }

# 20 GB free before each start: training at 500/200 reaches about 18.6 GB with the CUDA context
NEEDED_MIB=${NEEDED_MIB:-20000}
MIN_DISK_GB=${MIN_DISK_GB:-50}
ATTEMPTS=${ATTEMPTS:-3}
DATASETS="dataset1 dataset2_Java dataset2_CSharp dataset2_JavaScript dataset2_TypeScript"

wait_gpu() {
  local free
  while true; do
    free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
    if [ "$free" -ge "$NEEDED_MIB" ]; then
      echo "$(date -Is) GPU: ${free} MiB free; processes: $(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | tr '\n' ';')"
      return 0
    fi
    echo "$(date -Is) waiting for the GPU: ${free} MiB free, need ${NEEDED_MIB} MiB"
    sleep 300
  done
}

wait_disk() {
  local free
  while true; do
    free=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc '0-9')
    if [ "$free" -ge "$MIN_DISK_GB" ]; then return 0; fi
    echo "$(date -Is) waiting for disk: ${free} GB free, need ${MIN_DISK_GB} GB"
    sleep 300
  done
}

train() {  # $1 = name (dataset_mg)
  local name=$1 attempt ok
  if [ -f "$ROOT/markers/training_${name}.ok" ]; then
    echo "=== $name :: already trained, skipping ==="; return 0
  fi
  for attempt in $(seq 1 "$ATTEMPTS"); do
    # leftovers of an interrupted run
    rm -rf "MODELS/${name}" "AUX_FILES/${name}" "OUTPUT/${name}/model_${name}"
    rm -f "PROCESSED/${name}/processed_train.pkl" "PROCESSED/${name}/processed_valid.pkl" \
          "PROCESSED/${name}/processed_test.pkl"
    wait_disk
    wait_gpu
    echo "=== $name :: start $(date -Is) :: TRAINING_SEED=$TRAINING_SEED :: attempt $attempt ==="
    TRAINING_SEED=$TRAINING_SEED /usr/bin/time -o "LOGS/${name}_train_time.txt" -f "%E" \
      python run_mergegen.py "$name" train > "LOGS/${name}_train.log" 2>&1
    ok=$?
    echo "=== $name :: end $(date -Is) :: exit $ok :: $(tail -1 LOGS/${name}_train_time.txt 2>/dev/null) ==="
    if [ "$ok" -eq 0 ] && [ -f "MODELS/${name}/best_model.pt" ] \
       && grep -q "^time:" "OUTPUT/${name}/model_${name}/train_process" 2>/dev/null; then
      touch "$ROOT/markers/training_${name}.ok"
      return 0
    fi
    echo "=== $name :: failed, see LOGS/${name}_train.log ==="
  done
  return 1
}

check_jit() {  # $1 = arm whose test is used; 0 if the seven runs are complete
  python - "$1" <<'PY'
import json, os, sys
import pandas as pd
test_of = sys.argv[1]
suffix = "" if test_of == "mg" else f"__test_{test_of}"
pairs = [("dataset1", "dataset1"), ("dataset2_TypeScript", "dataset2_TypeScript"),
         ("dataset2_CSharp", "dataset2_CSharp"), ("dataset2_JavaScript", "dataset2_JavaScript"),
         ("dataset2_Java", "dataset2_Java"), ("dataset1", "dataset2_Java"), ("dataset2_Java", "dataset1")]
missing = 0
for ds, model in pairs:
    a = pd.read_csv(f"../data/split_{ds}_{test_of}.csv", dtype={"chunk_id": str})
    n = int((a.partition == "test").sum())
    d = f"JIT/{ds}_mg{suffix}/model_{model}_mg"
    ok = False
    if os.path.exists(f"{d}/times.csv") and os.path.exists(f"{d}/candidates.json"):
        try:
            ok = len(pd.read_csv(f"{d}/times.csv")) == n and len(json.load(open(f"{d}/candidates.json"))) == n
        except Exception:
            ok = False
    print(f"  {ds} <- {model}: {'complete' if ok else 'incomplete'} ({n} conflicts)")
    if not ok:
        missing += 1
        if os.path.exists(f"{d}/times.csv"):
            os.remove(f"{d}/times.csv")  # jit_inference.py skips a folder that has it
sys.exit(1 if missing else 0)
PY
}

for ROOT in $ROOTS; do
  export ROOT
  TRAINING_SEED=$(cat "$ROOT/training_seed.txt")
  [ -f "$ROOT/markers/sbcr.ok" ] || { echo "ERROR: $ROOT has no finished preparation"; exit 1; }
  cd "$ROOT/mergeGen"
  mkdir -p LOGS
  echo "##### partition $ROOT :: training seed $TRAINING_SEED :: $(date -Is) #####"

  for d in $DATASETS; do
    train "${d}_mg" || { echo "ERROR: training of ${d}_mg failed $ATTEMPTS times"; exit 1; }
  done

  if [ ! -f "$ROOT/markers/jit.ok" ]; then
    for attempt in 1 2; do
      wait_disk
      wait_gpu
      echo "=== JIT :: start $(date -Is) :: attempt $attempt ==="
      python "$REPO/mergegen/jit_inference.py" --root "$ROOT" --arm mg >> LOGS/jit.log 2>&1
      echo "=== JIT :: end $(date -Is) :: exit $? ==="
      if check_jit mg; then touch "$ROOT/markers/jit.ok"; break; fi
    done
    [ -f "$ROOT/markers/jit.ok" ] || { echo "ERROR: inference incomplete in $ROOT"; exit 1; }
  fi

  if [ -f "$ROOT/data/split_dataset1_pd.csv" ] && [ ! -f "$ROOT/markers/jit_common.ok" ]; then
    for attempt in 1 2; do
      wait_disk
      wait_gpu
      echo "=== JIT on the pd test :: start $(date -Is) :: attempt $attempt ==="
      python "$REPO/mergegen/jit_inference.py" --root "$ROOT" --arm mg --test-of pd >> LOGS/jit_common.log 2>&1
      echo "=== JIT on the pd test :: end $(date -Is) :: exit $? ==="
      if check_jit pd; then touch "$ROOT/markers/jit_common.ok"; break; fi
    done
    [ -f "$ROOT/markers/jit_common.ok" ] || { echo "ERROR: inference on the pd test incomplete in $ROOT"; exit 1; }
  fi
done
echo "##### GPU queue finished :: $(date -Is) #####"
