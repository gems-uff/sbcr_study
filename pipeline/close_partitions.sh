#!/usr/bin/env bash
# Closes the merge-grouped partitions: the similarity of both approaches, the comparison of each
# partition, the spread across partitions, the common set when there is one, and the manifests.
# Runs after the GPU and CPU queues.
#
#   ROOTS="<roots>" PARTITIONS="1=<root> 2=<root> 3=<root>" OUT=<spread folder> pipeline/close_partitions.sh
#
# ROOTS       roots whose similarities and comparison are computed; those of PARTITIONS not here are only read
# PARTITIONS  the number of each partition, for the spread
# LEAKAGE_FROM  optional: the root of the three arms; the `mg` rows of the leakage and common-set
#             analyses are redone with the root of ROOTS that has the common set, into
#             $LEAKAGE_FROM/<name of that root> (split-comparison/partition-1 in the archives)
REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOTS="${ROOTS:?set ROOTS, the roots to process}"
PARTITIONS="${PARTITIONS:?set PARTITIONS, as 1=<root> 2=<root> 3=<root>}"
OUT="${OUT:?set OUT, the folder of the spread}"
LEAKAGE_FROM="${LEAKAGE_FROM:-}"
export REPO
set -euo pipefail
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sbcr-analysis
mkdir -p "$OUT"

number() {  # the partition number of a root, by PARTITIONS
  local pair
  for pair in $PARTITIONS; do
    [ "${pair#*=}" = "$1" ] && { echo "${pair%%=*}"; return; }
  done
  echo "?"
}

for ROOT in $ROOTS; do
  for m in jit sbcr_evaluation; do
    [ -f "$ROOT/markers/$m.ok" ] || { echo "ERROR: $ROOT without $m.ok"; exit 1; }
  done
  echo "=== partition $(number "$ROOT") ($ROOT) :: $(date -Is) ==="
  python "$REPO/analysis/similarity/mergegen_similarity.py" --root "$ROOT" > "$ROOT/logs/similarity_mergegen.log" 2>&1
  python "$REPO/analysis/similarity/sbcr_similarity.py" --root "$ROOT" > "$ROOT/logs/similarity_sbcr.log" 2>&1
  python "$REPO/analysis/rq1_rq3/compare_approaches.py" --root "$ROOT" > "$ROOT/logs/consolidate.log" 2>&1
done

echo "=== spread :: $(date -Is) ==="
args=()
for pair in $PARTITIONS; do args+=(--partition "$pair"); done
python "$REPO/analysis/rq1_rq3/partition_spread.py" "${args[@]}" --out "$OUT" | tee "$OUT/spread.log"

if [ -n "$LEAKAGE_FROM" ]; then
  for ROOT in $ROOTS; do
    [ -f "$ROOT/markers/jit_common.ok" ] || continue
    echo "=== common set with the mg of $ROOT :: $(date -Is) ==="
    mkdir -p "$LEAKAGE_FROM/$(basename "$ROOT")"
    python "$REPO/analysis/rq1_rq3/leakage_effect.py" --root "$LEAKAGE_FROM" --mg-root "$ROOT" \
      --out "$LEAKAGE_FROM/$(basename "$ROOT")" | tee "$LEAKAGE_FROM/$(basename "$ROOT")/leakage_effect.log"
  done
fi

echo "=== manifests :: $(date -Is) ==="
for ROOT in $ROOTS; do
  python "$REPO/validation/manifest.py" write --root "$ROOT" --out "$OUT/partition-$(number "$ROOT").sha256" \
    --include 'splits/**/*' --include 'data/split_*.csv' --include 'mergeGen/JIT/**/*' --include 'sbcr/*/RESULTS/*.xlsx' \
    --include '*.csv' --include '*.txt' --aggregate 'sbcr/*/OUTPUT'
done
echo "=== closing finished :: $(date -Is) ==="
