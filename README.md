# Replication package of "Learning-based Generation vs. Search-based Combination for Merge Conflict Resolution: An Empirical Comparison of MergeGen and SBCR"

The paper compares two approaches to resolving merge conflicts on the same conflicts: MergeGen, which fine-tunes a language model (CodeT5-small) on resolved conflicts and generates the resolution, and SBCR, which searches for the combination of the lines of the two conflicting versions with the highest score. The conflicts come from open-source projects in Java, C#, JavaScript and TypeScript, in two datasets, and the study restricts them to conflicts the developers resolved by combination. It asks four questions:

- **RQ1**: how close each approach comes to the developer's resolution, and how long it takes, on the Java datasets;
- **RQ2**: whether the difference varies across languages;
- **RQ3**: how each approach performs when trained or tuned on the other Java dataset;
- **RQ4**: in which conflicts each approach falls short, by a qualitative coding of the conflicts in which one approach wins clearly or neither does, and a model of the characteristics that predict the winner.

This repository holds the code and the documentation. The data, the results and the trained models are in four archives (below). [`CLAIMS.md`](CLAIMS.md) maps each number, table and figure of the paper to the script that produces it and the file it is read from.

## Layout

| Folder | What it holds |
|---|---|
| `preparation/` | Dataset1 from its source, the combination filter, the three split designs, the chronological split, and the data of an experiment root |
| `mergegen/` | MergeGen: tokenization, training, just-in-time inference with the time of each step, and a smoke test of its environment ([`mergegen/README.md`](mergegen/README.md)) |
| `sbcr/` | SBCR: tuning, the selection of its configuration, evaluation ([`sbcr/README.md`](sbcr/README.md)) |
| `pipeline/` | The drivers that ran the experiments, in order ([`pipeline/README.md`](pipeline/README.md)) |
| `analysis/similarity/` | The similarity of both approaches to the resolution, and SBCR's conflicts above its size limit scored 0 |
| `analysis/rq1_rq3/` | The paired comparison of RQ1 to RQ3, the spread across splits and seeds, the times, the RQ3 gaps, the leakage and project-disjoint comparisons |
| `analysis/datasets/` | Population counts, partition sizes, shared merges, the resolution categories of Dataset2, the decoding of MergeGen's candidates |
| `analysis/chronological/` | The chronological split against the random ones |
| `analysis/rq4/` | The draw of the RQ4 sample, the packages, the coding at scale with the automatic annotator, the agreement report, the join of the labels with band and tool, and two checks of the results |
| `analysis/winner/` | The model of the characteristics that predict the winner (Python and R) |
| `analysis/figures/` | The two figures of the paper |
| `docs/` | The RQ4 coding protocol, the two versions of the annotator's instructions, and the prompt of the derivation of the categories |
| `environments/` | The lock of each conda environment, and the Dockerfile of an image for the analysis ([`environments/README.md`](environments/README.md)) |
| `validation/` | The manifest tool, and the logs of the validation |

Every script takes its paths from arguments or environment variables, and `--help` describes its inputs and outputs.

## Data

| Archive | What it holds | Size | License |
|---|---|---|---|
| Datasets | Dataset1 and Dataset2 as the scripts read them (`datasets/source`), and the data and splits of each experiment root | about 1 GB | CC BY 4.0 |
| Results | MergeGen's candidates and times, SBCR's spreadsheets and candidates, the similarities and every output the paper reads, organized by experiment root, with SHA-256 manifests | about 7 GB | CC BY 4.0 |
| Models | The MergeGen checkpoints of `partition-1`, one per dataset | 1.2 GB | Apache 2.0 |
| RQ4 | The draw, the packages of the sample and of the coding at scale, the coding sheet, the annotator's requests and responses, the outputs of the derivation, the agreement report of block 1 and the join of the labels, with a manifest | under 100 MB | CC BY 4.0 |

The archives are on FigShare: *link to be added*. Extract all four into one folder; the paths of [`CLAIMS.md`](CLAIMS.md) are relative to it. The experiment roots are `partition-1`, `partition-2` and `partition-3` (the three splits of the merge-grouped design), `partition-spread`, `partition-1-sbcr-seeds`, `split-comparison` (the random, merge-grouped and project-disjoint splits run side by side), `chronological`, and the folders of single analyses (`rq3-statistics`, `winner-model-two-predictors`, `consistency-checks` and others). `datasets/source` holds the two datasets as the submitted version of the study prepared them. The sources are the [SBES 2022 dataset](https://doi.org/10.6084/m9.figshare.26831818.v4) (Dataset1) and the [FSE 2022 dataset](https://doi.org/10.5281/zenodo.6366908) of Svyatkovskiy et al. (Dataset2), both CC BY 4.0 ([`LICENSES.md`](LICENSES.md)). The trace of Dataset1 reads the clone of [gems-uff/combination_conflicts_analysis](https://github.com/gems-uff/combination_conflicts_analysis) at commit `db8f9aa`.

The transcripts of the authors' discussions of the RQ4 cases are not published. They are in Portuguese and are available on request from the authors, with the scripts that split them by case and removed the passages that named an approach. The derivation prompt and the model's proposals of categories are published.

## Running it

Hardware of the study: an Intel Core i9-14900KF with 128 GB of RAM and an NVIDIA RTX 5090 with 32 GB. MergeGen's training and inference need a GPU; everything else runs on the CPU.

**The analysis.** Build the image of `environments/` and run the analysis scripts in it, with the code and the extracted archives mounted, for example:

```bash
docker build -t sbcr-study-analysis environments
docker run --rm --network none --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/work:ro -v /path/to/archives:/data:ro \
    -v /path/to/out:/out sbcr-study-analysis \
    conda run -n sbcr-analysis python analysis/rq1_rq3/compare_approaches.py --root /data/partition-1 --out /out
```

Or create the environments from their locks (`conda env create -f environments/<name>.lock.yml`) and run the scripts directly. The scripts that count tokens or decode candidates run in `mergegen-train`, the R models in `winner-model`, and the others in `sbcr-analysis`.

**SBCR.** `sbcr/sbcr_tuning.py` and `sbcr/sbcr_evaluate.py` run from `<root>/sbcr` on the partitions `preparation/prepare_sbcr.py` writes. The search is bounded by wall-clock time, so its candidates depend on the load of the machine ([`pipeline/README.md`](pipeline/README.md)).

**MergeGen.** `mergegen/environment/setup_env.sh` creates the inference environment and `verify_env.py` runs a checkpoint of the models archive on ten fixed conflicts. `mergegen/jit_inference.py` generates the candidates of a root. Training is documented in `pipeline/` and was not repeated.

**The tests.** Five scripts have tests on synthetic data, with no model call and no data of the archives:

```bash
conda run -n sbcr-analysis python analysis/rq1_rq3/test_rq3_gaps.py
conda run -n sbcr-analysis python analysis/rq4/test_join_scale.py
conda run -n sbcr-analysis python analysis/rq4/test_sbcr_candidate_origin.py
conda run -n sbcr-analysis python analysis/rq4/agreement/test_kappa_report.py
conda run -n sbcr-analysis python analysis/rq4/annotator/test_run_annotator.py
```

## What was validated

*To be completed with the validation of the package.* Three levels: the analysis, end to end in the image, from the archives as downloaded, with every output compared with the manifests of the archives; SBCR, one tuning and one evaluation on a small sample; and MergeGen, the smoke test and the inference of a checkpoint of `partition-1` on a few conflicts. The logs are in `validation/`.

## The submitted version

The version of this repository that went with the submitted paper is the tag `submitted-version`. Its full results are on FigShare, as cited in the paper.

## Licenses and citation

The code is MIT, except five files derived from the original MergeGen code, which has no license ([`mergegen/NOTICE.md`](mergegen/NOTICE.md)). The datasets, results and RQ4 archives are CC BY 4.0, and the models archive Apache 2.0, the license of CodeT5-small. Recreating three of the environments downloads packages of Anaconda's `defaults` channel, under Anaconda's terms. Details in [`LICENSES.md`](LICENSES.md). To cite the study, see [`CITATION.cff`](CITATION.cff).
