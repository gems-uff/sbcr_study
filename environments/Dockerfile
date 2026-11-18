# Image of the analysis part of the replication package.
#
# It holds three conda environments, created from their locks:
#   sbcr-analysis    similarities, statistics, RQ tables, RQ4 scripts and the figures
#   winner-model    R and lme4, for the model of the characteristics that predict the winner
#   mergegen-train  CodeT5's tokenizer (transformers 4.19.2), for the token counts
# and Git, whose `git merge-file` the token counts call. The image holds no code and no data:
# both are mounted when the container starts.
#
#   docker build -t sbcr-study-analysis environments
#   docker run --rm -it -v "$PWD":/work -v /path/to/data:/data sbcr-study-analysis
#   conda run -n sbcr-analysis python analysis/figures/paper_figures.py --root /data/...
#
# No GPU is needed. torch comes with the CUDA wheels of the lock and runs on the CPU.

# condaforge/miniforge3 (Ubuntu 24.04), the image in which the winner model with two
# predictors was rerun
FROM condaforge/miniforge3@sha256:7851b835559a6abb4aca37f5203bc48cc320894b17723498b1408266cdea1cd6

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Git 2.43.0 of Ubuntu 24.04, the version of the study, and a
# C++ compiler, since pylcs is published as source only and pip builds it
RUN apt-get update \
 && apt-get install -y --no-install-recommends git g++ \
 && rm -rf /var/lib/apt/lists/* \
 && git --version | grep -qx 'git version 2.43.0'

COPY sbcr-analysis.lock.yml winner-model.lock.yml mergegen-train.lock.yml /opt/locks/

# one layer per environment, so that a change to one lock rebuilds only that environment
RUN conda env create -q -f /opt/locks/sbcr-analysis.lock.yml && conda clean -afy
RUN conda env create -q -f /opt/locks/winner-model.lock.yml && conda clean -afy
RUN conda env create -q -f /opt/locks/mergegen-train.lock.yml && conda clean -afy

COPY check_image.sh /opt/locks/
RUN bash /opt/locks/check_image.sh

WORKDIR /work
CMD ["bash"]
