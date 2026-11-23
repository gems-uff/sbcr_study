# Claim map

From each number, table and figure of the paper to the script of this repository that produces it and the file of the archives it is read from. Paths of data are relative to the folder where the archives are extracted (`README.md`). `partition-1` is the split the paper reports, and `partition-2` and `partition-3` the two others of the merge-grouped design.

## Datasets and splits

| In the paper | Script | File |
|---|---|---|
| Dataset1 from 13,573 to 6,269 chunks, step by step | `preparation/dataset1/dataset1_trace.py`, `dataset1_sbes2022_filters.py` | `dataset1-trace/` |
| Longest version among the Dataset1 chunks used | `preparation/dataset1/dataset1_size_limit.py` | `partition-1/logs/dataset1_size_limit.log` |
| 816 projects of Dataset1; 282 projects, 806 merges and 871 identical conflicts shared with Dataset2_Java; the merge key of Dataset2 | `preparation/survey.py` | `dataset-overlap/` |
| The 151,426 conflicts of Dataset2, the seven categories per language, the 44,185 combination conflicts and the projects per language | `analysis/datasets/resolution_categories.py` | `dataset2-categories/` |
| Duplicate criterion and the duplicates removed per dataset | `preparation/make_splits.py`, `analysis/datasets/partition_sizes.py` | `split-comparison/splits/summary.csv`, `partition-1/partition_sizes.csv` |
| Partition sizes (Table of the partitions, Figure of the datasets) | `analysis/datasets/partition_sizes.py` | `partition-1/partition_sizes.csv` |
| Merge key, joint split of the Java datasets, 5% cap and acceptance test | `preparation/make_splits.py`, `pipeline/prepare_partition.sh` | `partition-<n>/splits/acceptance_check.csv`, `partition-<n>/logs/splits.log` |
| Merges above the 5% cap: 0.7% to 16.4% of a dataset | `analysis/datasets/cap_share.py` | from `partition-<n>/splits/mg/` |
| Seeds and test sizes of the three splits | `pipeline/prepare_partition.sh` | `partition-<n>/draw_seed.txt`, `training_seed.txt`, `splits/summary.csv` |
| Overlap of the three test partitions | `analysis/datasets/test_overlap.py` | from `partition-<n>/splits/mg/` |
| Shared merge commits under another project name | `analysis/datasets/shared_commits.py` | `consistency-checks/shared-merge-commits/` |
| Largest project and largest group in the test | `analysis/datasets/largest_test_group.py` | `consistency-checks/largest-test-group/` |
| Project-disjoint and random splits; three to four times more combination conflicts | `preparation/make_splits.py` | `split-comparison/splits/summary.csv` |
| Chronological split | `preparation/commit_dates.py`, `preparation/chronological_split.py` | `commit-dates/`, `chronological/splits/` |

## Configuration of the approaches

| In the paper | Script | File |
|---|---|---|
| Training times of MergeGen | `pipeline/gpu_queue.sh` | `partition-1/mergeGen/LOGS/*_train_time.txt` |
| SBCR's grid, tuning set, selection rule and configurations (Table of the tuning) | `sbcr/sbcr_tuning.py`, `sbcr/select_configuration.py` | `partition-1/selected_configurations.csv`, `partition-1/sbcr/tuning_*/` |
| SBCR's 20,000-character limit and its effect, at most 0.0002 | `analysis/similarity/sbcr_scores.py`, `analysis/rq1_rq3/compare_approaches.py` | `partition-1/comparison.csv`, rows `*_excluding_out_of_limits` |
| How SBCR's timeout works | `sbcr/sbcr_evaluate.py` | |
| The RQ4 coding protocol, session dates, derivation, the frozen scheme and the automatic annotator | `docs/rq4-coding-protocol.md`, `docs/derivation-prompt.md`, `docs/annotator-instructions-v0.md`, `docs/annotator-instructions-v1.md` | `analysis/rq4/scheme/coding-scheme.json`, `rq4/derivation/`, `rq4/annotator/` |

## RQ1 to RQ3

| In the paper | Script | File |
|---|---|---|
| Table of the similarity of RQ1 and RQ2; RQ1 and RQ2 differences, Wilcoxon p, exact match | `analysis/rq1_rq3/compare_approaches.py` | `partition-1/comparison.csv` |
| Spread across the three splits; order of the languages; p of 4.4e-15 or less | `analysis/rq1_rq3/partition_spread.py` | `partition-spread/partition_spread.csv`, `spread.log` |
| MergeGen higher with every SBCR seed | `analysis/rq1_rq3/seed_spread.py` | `partition-1-sbcr-seeds/seed_summary.csv`, `comparison_per_seed.csv` |
| MergeGen higher on the project-disjoint split | `analysis/rq1_rq3/project_disjoint_comparison.py` | `project-disjoint-comparison/` |
| Leakage comparison | `analysis/rq1_rq3/leakage_effect.py` | `split-comparison/leakage_effect.csv`, `common_set.csv`, and `split-comparison/partition-1/` with the model of `partition-1` |
| Table of the times of RQ1 and RQ2; conflicts past SBCR's timeout; share of the preprocessing | `analysis/rq1_rq3/times_per_language.py` | `partition-1/times_per_language.csv` |
| SBCR faster in 324 of 549 Dataset1 conflicts | `analysis/rq1_rq3/faster_slower_counts.py` | `consistency-checks/sbcr-faster-share.log` |
| Figure of the times of RQ1 and RQ2 | `analysis/figures/paper_figures.py` | `rq1-rq2-time.pdf`, from `partition-1/mergeGen/JIT/*/*/times.csv` and `partition-1/sbcr/` |
| Table of RQ3; the RQ3 gaps and their direct comparison | `analysis/rq1_rq3/rq3_gaps.py` | `rq3-statistics/rq3_gaps_s3022024.csv`, `rq3_gap_difference_s3022024.csv` |
| RQ3 with the five SBCR seeds | `analysis/rq1_rq3/seed_spread.py` | `partition-1-sbcr-seeds/seed_summary.csv` |
| Chronological split and its effects | `analysis/chronological/chronological_effects.py` | `chronological/effects/` |

## RQ4

| In the paper | Script | File |
|---|---|---|
| Bands and their thresholds (Table of the bands) | `analysis/rq4/build_scale.py` | `rq4/scale/bands.csv`, `draw.json` |
| Figure of the bands | `analysis/figures/paper_figures.py` | `rq4-bands.pdf`, from `partition-1` and `rq4/scale/` |
| The coding scheme (Table of the scheme) | | `analysis/rq4/scheme/coding-scheme.json` |
| Kappas of block 1 | `analysis/rq4/agreement/kappa_report.py` | `rq4/agreement/block1/kappa_report.md` |
| The 1,979 conflicts labeled, the 6 above the annotator's limit, frequencies per band (Table of the frequencies) | `analysis/rq4/annotator/run_scale.sh`, `analysis/rq4/join_scale.py` | `rq4/annotator/`, `rq4/sealed/scale/join/frequencies.csv`, `joined.csv`, `block1.csv` |
| F5 and FN against MergeGen's limits | `analysis/rq4/band_code_checks.py` | `consistency-checks/band-codes-against-limits/` |
| MergeGen's limits on the test (Table of the limits) | `analysis/datasets/population_tokens.py`, `population_candidates.py`, `tabulate_population.py` | `partition-1/population_table.csv`, `population_tokens.csv` |
| SBCR's candidates made of the lines of one version or the base; its evaluation function against the resolution | `analysis/rq4/sbcr_candidate_origin.py` | `rq4/sealed/sbcr-candidate-origin/report.md` |
| The model of the characteristics that predict the winner: coefficients, R², AUC, bootstrap, ties per quartile of the imbalance, cells of the routing rule | `analysis/winner/build_table.py`, `fit_models.R`, `bootstrap_main.R`, `ties_by_imbalance.py` | `winner-model-two-predictors/`, `winner-model-three-predictors/conflicts.csv`, `ties_by_imbalance.csv` |
| 4,413 conflicts from 1,590 projects and 2,486 merges | `analysis/winner/build_table.py` | `winner-model-three-predictors/conflicts.csv` |
