# SBCR

Tuning and evaluation of SBCR, the search-based approach of the study, and the two scripts that select its configuration and resume interrupted evaluations.

| File | What it does |
|---|---|
| `sbcr_tuning.py` | Runs every configuration of the grid on 100 conflicts drawn from the training partition |
| `select_configuration.py` | Chooses the configuration of each dataset: the highest mean similarity, and within 0.005 of it the lowest mean time |
| `sbcr_evaluate.py` | Evaluates one configuration on the test conflicts, with the seed of `SEED` (3022024 by default) |
| `resume_evaluations.py` | Reruns only the evaluations that did not finish, since `sbcr_evaluate.py` does not resume |

Both search scripts run from `<root>/sbcr`, read the partitions of `preparation/prepare_sbcr.py` in `<root>/data`, and write one folder per run, named by their last argument. The search is bounded by wall-clock time, so the number of processes running at once changes the result: the study ran five at a time on 24 cores (`pipeline/README.md`).

**The 20,000-character limit.** SBCR does not search a conflict with a version of 20,000 characters or more. It records it as `OUT_OF_LIMITS`, and the analyses score it 0 (`analysis/similarity/sbcr_scores.py`).
