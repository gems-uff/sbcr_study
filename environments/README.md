# Environments

The conda environments the study ran in, one lock file each, and the Dockerfile of an image for the analysis part. The locks are the output of `conda env export` on the machine of the experiments, with the version and build of every conda package and the exact version of every pip package, for Linux x86-64.

| Lock | What runs in it |
|---|---|
| `mergegen-repl.lock.yml` | MergeGen's just-in-time inference and its smoke test (Python 3.9.23, torch 2.8.0+cu129, transformers 4.19.2) |
| `mergegen-train.lock.yml` | MergeGen's training, and CodeT5's tokenizer for the token counts and the decoding of candidates: the inference environment plus `accelerate` 0.18.0 and `psutil` |
| `sbcr-analysis.lock.yml` | The preparation, SBCR, the similarities and statistics, the RQ4 scripts and the automatic annotator, and the figures (Python 3.11.16, pandas 3.0.5, NumPy 2.4.6, SciPy 1.17.1, pylcs 0.1.1, matplotlib 3.10.0, anthropic) |
| `winner-model.lock.yml` | The R models of `analysis/winner` (R 4.4.3, lme4 2.0-6, from conda-forge) |

```bash
conda env create -f environments/sbcr-analysis.lock.yml
```

`pylcs` 0.1.1 is published on PyPI as source only, so creating `sbcr-analysis` needs a C++ compiler on the machine. pip builds it with the newest `setuptools` and `pybind11` on PyPI at build time.

The two MergeGen environments install `torch==2.8.0+cu129` from the PyTorch package index, which their locks name. `mergegen/environment/setup_env.sh` creates `mergegen-repl` and checks it.

**Anaconda's `defaults` channel.** `mergegen-repl`, `mergegen-train` and `sbcr-analysis` name Anaconda's `defaults` channel, so recreating them, or building the image below, downloads packages from `repo.anaconda.com` under the [Anaconda Terms of Service](https://www.anaconda.com/legal/terms/terms-of-service). They are free for individuals, for universities, for non-profit and research organizations, and for for-profit organizations of up to 200 people, and require a paid plan above that. The locks list names, versions and builds, and redistribute no package.

## The analysis image

One image with `sbcr-analysis`, `winner-model` and `mergegen-train` (for CodeT5's tokenizer, on the CPU), created from their locks, Git 2.43.0 and a C++ compiler. It holds no code and no data: both are mounted when the container starts. The base image is pinned by its digest. The last layer runs `check_image.sh`, which compares the packages of each environment with its lock and imports what the scripts need, so a build whose environments differ from the locks fails.

```bash
docker build -t sbcr-study-analysis environments
docker run --rm --network none --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$PWD":/work:ro -v /path/to/partition-1:/data/partition-1:ro -v /path/to/rq4:/data/rq4:ro -v /path/to/out:/out \
    sbcr-study-analysis \
    conda run -n sbcr-analysis python analysis/figures/paper_figures.py --root /data/partition-1 \
        --scale /data/rq4/scale --out /out
```

The image takes about 17 GB, most of it torch and its CUDA libraries, which come with `mergegen-train`. MergeGen's inference and training need the GPU and run outside the image, in `mergegen-repl` and `mergegen-train`.
