#!/usr/bin/env bash
# Recreates the MergeGen inference environment from its lock and checks its dependencies.
#
# Input: environments/mergegen-repl.lock.yml. Output: the conda environment (default name
# mergegen-repl). Needs conda, git and an NVIDIA driver with CUDA 12.9 support; the torch
# wheel brings its CUDA libraries.
#
#   mergegen/environment/setup_env.sh [name]
set -euo pipefail

ENV_NAME="${1:-mergegen-repl}"
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

echo
echo "Environment '$ENV_NAME' created. Run the smoke test with a checkpoint of the models archive:"
echo "  conda activate $ENV_NAME"
echo "  python $HERE/verify_env.py --backbone <dir>/codet5-small-local --checkpoint <models>/dataset2_Java_mg/best_model.pt --reference dataset2_Java_mg"
