# Pipeline

The drivers that ran the experiments, in the order they ran. Each experiment root is a folder outside this repository that holds the data, the splits, the MergeGen code and outputs (`mergeGen/`), the SBCR outputs (`sbcr/`) and the logs of one run of the pipeline. The archives hold the roots the paper reads (`partition-1` to `partition-3`, `split-comparison`, `chronological` and the others), without the trained models except those of `partition-1`, and without the tokenized intermediates, which the drivers rebuild.

Every driver takes its paths from environment variables, and none of them needs to run from a given folder. They use the conda environments of `environments/`: `sbcr-analise` for the preparation and SBCR, `mergegen-train` for MergeGen.

## The three partitions of the merge-grouped design

The design the paper reports. Each driver is idempotent: it records a marker in `<root>/markers` for each step it finishes, and resumes from where it stopped.

| Driver | What it does |
|---|---|
| `prepare_partition.sh` | Split with the draw seed and the rule (`RULE=cap CAP=0.05`), acceptance test, data, tokenization, cut references and the partitions SBCR reads; with `PD_FROM`, the `pd` partitions of another root, for the common set |
| `gpu_queue.sh` | Training of the five MergeGen models with the seed of `training_seed.txt`, and the just-in-time inference of the seven runs; with the `pd` partitions, also the inference on the test of `pd`. One GPU, in series |
| `sbcr_queue.py` | SBCR tuning, selection of the configuration and evaluation, in a global queue of five slots, with a guard against the load of other users |
| `close_partitions.sh` | Similarities, comparison of each partition, spread across partitions, the common set and the manifests |

The seeds of the three partitions are in `draw_seed.txt` and `training_seed.txt` of each root. With them, the partitions were made as follows:

```bash
ROOT=<partition-1> DRAW_SEED=$(cat <partition-1>/draw_seed.txt) RULE=cap TOLERANCE=0.05 \
    DATA_ROOT=<datasets/source> BACKBONES=<dir> PD_FROM=<split-comparison> pipeline/prepare_partition.sh
ROOTS="<partition-1> <partition-2> <partition-3>" pipeline/gpu_queue.sh
python pipeline/sbcr_queue.py --roots "<partition-1> <partition-2> <partition-3>"
ROOTS="<partition-1> <partition-2> <partition-3>" PARTITIONS="1=<partition-1> 2=<partition-2> 3=<partition-3>" \
    OUT=<partition-spread> LEAKAGE_FROM=<split-comparison> pipeline/close_partitions.sh
```

The five SBCR seeds of `partition-1-sbcr-seeds` come from `sbcr_queue.py --seeds 20260904 7412 98765 31337` on the root of partition 1. The chronological split runs the same drivers on a root whose `splits/` comes from `preparation/chronological_split.py`.

## The split comparison

The three arms run side by side on one root (`split-comparison`): the random split (`random`), the merge-grouped split (`mg`) and the project-disjoint split (`pd`), with `preparation/make_splits.py --rule largest-first`. Its project-disjoint arm is the sensitivity analysis of the paper.

| Driver | What it does |
|---|---|
| `split_comparison/tokenize.sh` | Tokenizes each dataset once, shared by the three arms |
| `split_comparison/pipeline.sh` | Waits for the tokenization, links it to the arms and runs `train.sh` |
| `split_comparison/train.sh` | The fifteen MergeGen models, waiting for 20 GB of free GPU memory before each |
| `split_comparison/jit.sh` | Candidates and times per step of every test conflict, in the three arms |
| `split_comparison/common.sh` | The models of `random` and `mg` on the test partition of `pd` |
| `split_comparison/tune_queue.sh` | The fifteen SBCR tunings, in a queue of five slots |
| `split_comparison/evaluate.sh` | The selection rule, then the SBCR evaluations with five seeds and the two crossed ones of RQ3 |
| `split_comparison/common_sbcr.sh` | SBCR on the test partition of `pd` with the configurations of `random` and `mg` |

`sbcr/resume_evaluations.py` resumes the evaluations that a restart of the machine interrupted.

## Concurrency

SBCR's search is bounded by wall-clock time, so a process that gets less CPU completes fewer iterations and returns a different candidate. Every SBCR queue keeps at most five processes on the machine (24 physical cores), counting those of other queues, and `sbcr_queue.py` stops launching while the load average is above 24 and redoes the tasks that ran under an overload. The times the paper reports were measured with this concurrency, on an Intel Core i9-14900KF with an NVIDIA RTX 5090.
