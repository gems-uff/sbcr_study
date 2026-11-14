#!/usr/bin/env bash
# Links the MergeGen code folder to its data, backbones and output folders.
#
# The MergeGen code resolves everything relative to its own folder: `./codet5-small-local`,
# `PROCESSED/`, `MODELS/`, `AUX_FILES/`, `../data/`. The script links them from where they are.
# Experiment roots do not need it: preparation/prepare_data.py sets them up.
#
#   MERGEGEN_DATA_ROOT=<dir> MERGEGEN_BACKBONES=<dir> mergegen/setup_workdir.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${MERGEGEN_DATA_ROOT:?set MERGEGEN_DATA_ROOT, the folder of the data and outputs}"
BACKBONES="${MERGEGEN_BACKBONES:?set MERGEGEN_BACKBONES, the folder with codet5-small-local}"

echo "data and outputs: $DATA"
echo "backbones:        $BACKBONES"
echo

for d in PROCESSED AUX_FILES MODELS OUTPUT RESULTS LOGS; do
  mkdir -p "$DATA/$d"
  if [ -e "$HERE/$d" ]; then
    echo "  already there: $d"
  else
    ln -s "$DATA/$d" "$HERE/$d"; echo "  link created: $d"
  fi
done

for b in codet5-small-local; do
  if [ -e "$HERE/$b" ]; then
    echo "  already there: $b"
  elif [ -d "$BACKBONES/$b" ]; then
    ln -s "$BACKBONES/$b" "$HERE/$b"; echo "  link created: $b"
  else
    echo "  MISSING: $BACKBONES/$b (download Salesforce/codet5-small)"
  fi
done

echo
echo "Check the configuration before training:"
echo "  python training/apply_config.py --dir . --check original_test_batch_1"
