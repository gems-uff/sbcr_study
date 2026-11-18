#!/usr/bin/env bash
# Checks the environments of the analysis image: the packages of each one, with version and build,
# against its lock, and the imports the analysis scripts need. The Dockerfile runs it, so an image
# that does not match its locks fails to build.
#
#   bash check_image.sh [folder of the locks]     # default: the folder of this script
set -euo pipefail

LOCKS="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

packages() {
  sed -n '/^dependencies:/,$p' | grep -vE '^prefix: |--extra-index-url'
}

for env in sbcr-analysis winner-model mergegen-train; do
  if diff <(packages < "$LOCKS/$env.lock.yml") <(conda env export -n "$env" | packages); then
    echo "$env: packages as in $env.lock.yml"
  else
    echo "$env: packages differ from $env.lock.yml" >&2
    exit 1
  fi
done

conda run -n sbcr-analysis python -c "
import matplotlib, numpy, openpyxl, pandas, pylcs, scipy
print('sbcr-analysis: matplotlib', matplotlib.__version__, 'pandas', pandas.__version__)"
conda run -n winner-model Rscript -e "suppressMessages(library(lme4)); cat('winner-model: R', as.character(getRversion()), 'lme4', as.character(packageVersion('lme4')), '\n')"
conda run -n mergegen-train python -c "
import transformers
from transformers import RobertaTokenizer
print('mergegen-train: transformers', transformers.__version__)"
git --version
