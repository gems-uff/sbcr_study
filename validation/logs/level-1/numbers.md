# Level 1: outputs checked by number

## Outputs the archives do not hold

Three scripts print their result in place of writing a file, and the figures are not in the archives. Each is compared with the paper.

| Script | Result | In the paper |
|---|---|---|
| `analysis/datasets/cap_share.py`, on each of `partition-1` to `partition-3` | Merges above the 5% cap hold 0.7% (Dataset2_Java) to 16.4% (Dataset2_CSharp) of the conflicts of a dataset, the same on the three splits (`printed/cap_share_partition-<n>.txt`) | 0.7% to 16.4% |
| `analysis/datasets/test_overlap.py` | Overlap of the test partitions of the three splits: 7.3% to 14.9% between two splits, 0.3% to 2.5% in all three (`printed/test_overlap.txt`) | 7.3% to 14.9%, 0.3% to 2.5% |
| `analysis/rq1_rq3/faster_slower_counts.py` | SBCR faster in 324 of the 549 paired conflicts of Dataset1, slower in 225, no tie; equal to `consistency-checks/sbcr-faster-share.log` | 324 of 549 |
| `analysis/figures/paper_figures.py` | `rq1-rq2-time.pdf` (SHA-256 `2fec02fe…`) and `rq4-bands.pdf` (`aa68bd83…`) | The same bytes as the two figures of the paper |

## The model of the characteristics that predict the winner

`fit_models.R` and `bootstrap_main.R` in `winner-model`. Largest absolute difference against the archived file, over all numeric cells, and the cells whose value rounded to three decimals changes:

| Folder | `coefficients.csv` | `fit.csv` | `cells.csv` | `bootstrap_main.csv` | Change at three decimals |
|---|---|---|---|---|---|
| `winner-model-three-predictors` | 0 | 0 | 0 | 0 | none |
| `winner-model-two-predictors/stored/two` | 7.10e-06 | 4.97e-07 | 0 | 0 | none |
| `winner-model-two-predictors/stored/three` | 3.54e-06 | 7.54e-07 | 0 | not written | none |
| `winner-model-two-predictors/decoded/two` | 1.23e-05 | 2.06e-06 | 0 | 0 | none |
| `winner-model-two-predictors/decoded/three` | 4.88e-06 | 1.96e-07 | 0 | not written | none |

The archived fits of `winner-model-two-predictors` ran in a container on another computer, and those of `winner-model-three-predictors` on the machine of this validation. The logs of the fits (`fit_models.log`, `fit_models.stdout`, `bootstrap_main.log`) differ in the same digits, in the line of `sessionInfo()` that names the release of Ubuntu (24.04.4 against 24.04.5), and in the order in which R interleaves its messages with its output.

## Other outputs that differ in content

- `rq4/sealed/sbcr-candidate-origin/report.md`: the line of the run gives the commit of the code, which the archived report leaves out. The counts that follow on the line, and the rest of the report, are equal. `report.json` differs in the same fields (class provenance).

## The RQ4 join and the agreement report

`join_scale.py` and `kappa_report.py` wrote the reports of `rq4/sealed/scale/join/` and `rq4/agreement/block1/` from the archives as published, the coding sheet without the history of the coding included. A rerun gives `joined.csv`, `frequencies.csv`, `block1.csv` and `sample_tools.csv` byte for byte, and reports that differ from the archived ones in the date of the run and, for `join_report`, in the absolute paths of the input folders.

## Known difference

`partition-spread/common_set.log` and `partition-spread/common_set/`: the archived files compare the similarity with whitespace, and `leakage_effect.py` compares it with all whitespace removed. The run gives files byte-identical to `split-comparison/partition-1/common_set.csv` and `leakage_effect.csv`, the same analysis, and differs from `partition-spread/common_set/` by up to 0.057 in the gaps.
