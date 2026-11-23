#!/usr/bin/env bash
# Recreates the MergeGen inference environment from its lock, checks its dependencies and, given
# the models and the backbone, runs the smoke test of verify_env.py on every checkpoint.
#
# Input: environments/mergegen-repl.lock.yml; optionally the MODELS folder of the models archive
# and the folder codet5-small-local (a copy of Salesforce/codet5-small). Output: the conda
# environment (default name mergegen-repl) and the report of verify_env.py. Needs conda, git and
# an NVIDIA driver with CUDA 12.9 support; the torch wheel brings its CUDA libraries.
#
#   mergegen/environment/setup_env.sh [--name mergegen-repl] \
#       [--models <archives>/partition-1/mergeGen/MODELS --backbone <dir>/codet5-small-local]
set -euo pipefail

ENV_NAME="mergegen-repl"
MODELS=""
BACKBONE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) ENV_NAME="$2"; shift 2;;
    --models) MODELS="$2"; shift 2;;
    --backbone) BACKBONE="$2"; shift 2;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown argument: $1 (see --help)"; exit 1;;
  esac
done
if { [ -n "$MODELS" ] && [ -z "$BACKBONE" ]; } || { [ -z "$MODELS" ] && [ -n "$BACKBONE" ]; }; then
  echo "--models and --backbone go together"; exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK="$HERE/../../environments/mergegen-repl.lock.yml"

command -v conda >/dev/null || { echo "conda not found on the PATH"; exit 1; }
command -v git   >/dev/null || { echo "git not found on the PATH (used by git merge-file)"; exit 1; }
command -v nvidia-smi >/dev/null || echo "warning: nvidia-smi not found; MergeGen will fall back to the CPU"

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "The environment '$ENV_NAME' already exists. Remove it before recreating it:"
  echo "  conda env remove -n $ENV_NAME"
  exit 1
fi

echo "==> creating '$ENV_NAME' from $LOCK"
conda env create -n "$ENV_NAME" -f "$LOCK"

echo "==> checking the consistency of the dependencies"
conda activate "$ENV_NAME"
pip check

if [ -z "$MODELS" ]; then
  echo
  echo "Environment '$ENV_NAME' created. Run the smoke test with a checkpoint of the models archive:"
  echo "  conda activate $ENV_NAME"
  echo "  python $HERE/verify_env.py --backbone <dir>/codet5-small-local --checkpoint <models>/dataset2_Java_mg/best_model.pt --reference dataset2_Java_mg"
  exit 0
fi

status=0
for checkpoint in "$MODELS"/*/best_model.pt; do
  name="$(basename "$(dirname "$checkpoint")")"
  echo
  echo "==> smoke test of $name"
  python "$HERE/verify_env.py" --backbone "$BACKBONE" --checkpoint "$checkpoint" --reference "$name" || status=1
done
exit $status
