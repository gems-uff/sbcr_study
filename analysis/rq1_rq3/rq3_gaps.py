#!/usr/bin/env python3
"""Generalization gaps of RQ3: each approach against itself across the two training sets.

RQ3 tests each approach on Dataset1 and on Dataset2_Java with the configuration of the same
dataset (own) and with that of the other dataset (other). The four comparisons are SBCR and
MergeGen on each test set, paired on the same conflicts:

- SBCR targets `dataset1` against `rq3_ds1`, and `dataset2_Java` against `rq3_java`;
- MergeGen models `dataset1_mg` against `dataset2_Java_mg` on the Dataset1 test set, and the
  reverse on the Dataset2_Java test set.

For each comparison: the gap (own − other, mean of the per-conflict differences) with its 95%
interval by the normal approximation; the two-sided Wilcoxon signed-rank test and the paired
rank-biserial correlation, own first; Holm's correction over the four p-values; the descriptive
columns of each configuration and the shares of conflicts each one wins.

Direct comparison of the two gaps: on each test set, per conflict, SBCR's gap minus MergeGen's
gap, with its 95% interval, the Wilcoxon test and the paired rank-biserial of these differences,
the shares of conflicts in which SBCR's gap is larger, equal and smaller, and Holm's correction
over the two tests, as a family of their own.

The similarity is `sim_lcs_no_whitespace`, and SBCR scores 0 above its size limit. SBCR enters
with the seeds of `--sbcr-seeds`: one seed alone, or the mean over several per conflict. Every
seed must cover every conflict under both configurations. Ties count only exact zeros, as the
Wilcoxon test does, and the run stops if a per-conflict difference is above 0 and below 10⁻¹²
in absolute value, a floating-point residue of subtracting two equal quantities.

Input: the root of partition 1 (`--root`).
Outputs, in `--out`, named after the seeds: `rq3_gaps_s<seeds>.csv` (the four comparisons),
`rq3_gap_difference_s<seeds>.csv` (the direct comparison) and `rq3_gaps_s<seeds>.json`
(parameters, commit and hashes of the inputs).

    python analysis/rq1_rq3/rq3_gaps.py --root <root> --sbcr-seeds 3022024 --out <dir> [--check-against-comparison]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from compare_approaches import evaluated_sets, load_mergegen, paired_rank_biserial, split_key  # noqa: E402
from sbcr_scores import SIM, load_sbcr_similarities  # noqa: E402

CHRONO = os.path.normpath(os.path.join(HERE, "..", "chronological"))
sys.path.insert(0, CHRONO)
from chronological_effects import holm  # noqa: E402

ARM = "mg"
# test set -> (SBCR target with the own configuration, with the other dataset's configuration)
SBCR_TARGETS = {"dataset1": ("dataset1", "rq3_ds1"), "dataset2_Java": ("dataset2_Java", "rq3_java")}
OTHER = {"dataset1": "dataset2_Java", "dataset2_Java": "dataset1"}
COMPARISON_TOLERANCE = 1e-12
RESIDUE_TOLERANCE = 1e-12


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sbcr_by_target(sb, seeds, evaluated):
    """SBCR similarity and exact match per conflict for each RQ3 target, averaged over `seeds`.

    Stops unless each seed has exactly the conflicts of the test set under each target.
    """
    sb = sb[(sb.arm == ARM) & (sb.partition == ARM)]
    out = {}
    for test_set, targets in SBCR_TARGETS.items():
        expected = evaluated[split_key(test_set, ARM)]
        for target in targets:
            t = sb[sb.target == target]
            for seed in seeds:
                ids = t.loc[t.seed == seed, "chunk_id"]
                if ids.duplicated().any() or set(ids) != expected:
                    raise RuntimeError(f"SBCR seed {seed}, target {target}: {ids.nunique()} conflicts, "
                                       f"expected the {len(expected)} of the test set")
            out[target] = (t.groupby("chunk_id")
                           .agg(sim=(SIM, "mean"), em=("exact_match_full", "mean"))
                           .reset_index())
    return out


def mergegen_by_model(mg, evaluated):
    """MergeGen similarity and exact match per conflict, keyed by (test set, model)."""
    out = {}
    for test_set in SBCR_TARGETS:
        expected = evaluated[split_key(test_set, ARM)]
        for model in (test_set, OTHER[test_set]):
            t = mg[(mg.dataset == test_set) & (mg.arm == ARM) & (mg.model == model)]
            if t.chunk_id.duplicated().any() or set(t.chunk_id) != expected:
                raise RuntimeError(f"MergeGen model {model} on {test_set}: {t.chunk_id.nunique()} conflicts, "
                                   f"expected the {len(expected)} of the test set")
            out[(test_set, model)] = t.rename(columns={"mergegen": "sim", "mergegen_em": "em"})[
                ["chunk_id", "sim", "em"]]
    return out


def check_ties(d):
    """Stop if a per-conflict difference is a floating-point residue rather than a tie."""
    residues = int(((d != 0) & (d.abs() < RESIDUE_TOLERANCE)).sum())
    if residues:
        raise RuntimeError(f"{residues} per-conflict differences are above 0 and below {RESIDUE_TOLERANCE} "
                           "in absolute value, residues of a tie the test would count as a difference")


def compare(own, other):
    """Paired comparison of one approach with its own and with the other configuration.

    `own` and `other` are frames with `chunk_id`, `sim` and `em` on the same conflicts.
    The gap is own − other: positive when the approach scores lower with the other
    dataset's configuration.
    """
    j = own.merge(other, on="chunk_id", suffixes=("_own", "_other"), validate="one_to_one")
    if len(j) != len(own) or len(j) != len(other):
        raise RuntimeError("the two configurations do not cover the same conflicts")
    a, b = j.sim_own, j.sim_other
    d = a - b
    check_ties(d)
    n = len(d)
    half = 1.96 * d.std(ddof=1) / np.sqrt(n)
    _, p = wilcoxon(a, b)
    return {"n": n,
            "own_mean": a.mean(), "own_sd": a.std(), "own_median": a.median(), "own_exact": j.em_own.mean(),
            "other_mean": b.mean(), "other_sd": b.std(), "other_median": b.median(),
            "other_exact": j.em_other.mean(),
            "gap": d.mean(), "ci_low": d.mean() - half, "ci_high": d.mean() + half,
            "own_closer": (d > 0).mean(), "tie": (d == 0).mean(), "other_closer": (d < 0).mean(),
            "rank_biserial": paired_rank_biserial(a, b), "p": p}


def gaps(sbcr, mergegen):
    """The four comparisons of the family, with Holm's correction over their p-values."""
    rows = []
    for test_set, (own_target, other_target) in SBCR_TARGETS.items():
        rows.append({"approach": "SBCR", "test_set": test_set, "own": own_target, "other": other_target,
                     **compare(sbcr[own_target], sbcr[other_target])})
    for test_set in SBCR_TARGETS:
        rows.append({"approach": "MergeGen", "test_set": test_set, "own": f"model_{test_set}_{ARM}",
                     "other": f"model_{OTHER[test_set]}_{ARM}",
                     **compare(mergegen[(test_set, test_set)], mergegen[(test_set, OTHER[test_set])])})
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t.p)
    t["detectable"] = t.p_holm < 0.05
    t["ci_excludes_zero"] = (t.ci_low > 0) | (t.ci_high < 0)
    return t


def gap_per_conflict(own, other):
    """own − other per conflict, indexed by chunk id, on the same conflicts."""
    j = own.merge(other, on="chunk_id", suffixes=("_own", "_other"), validate="one_to_one")
    if len(j) != len(own) or len(j) != len(other):
        raise RuntimeError("the two configurations do not cover the same conflicts")
    return (j.sim_own - j.sim_other).set_axis(j.chunk_id)


def gap_difference(sbcr, mergegen):
    """SBCR's gap minus MergeGen's gap per conflict, on each test set, with Holm over the two tests.

    Positive when SBCR loses more than MergeGen with the other dataset's configuration.
    """
    rows = []
    for test_set, (own_target, other_target) in SBCR_TARGETS.items():
        g_sbcr = gap_per_conflict(sbcr[own_target], sbcr[other_target])
        g_mg = gap_per_conflict(mergegen[(test_set, test_set)], mergegen[(test_set, OTHER[test_set])])
        if set(g_sbcr.index) != set(g_mg.index):
            raise RuntimeError(f"SBCR and MergeGen do not cover the same conflicts on {test_set}")
        g_mg = g_mg.loc[g_sbcr.index]
        d = g_sbcr - g_mg
        check_ties(d)
        n = len(d)
        half = 1.96 * d.std(ddof=1) / np.sqrt(n)
        _, p = wilcoxon(g_sbcr, g_mg)
        rows.append({"test_set": test_set, "n": n, "sbcr_gap": g_sbcr.mean(), "mergegen_gap": g_mg.mean(),
                     "difference": d.mean(), "ci_low": d.mean() - half, "ci_high": d.mean() + half,
                     "sbcr_gap_larger": (d > 0).mean(), "equal": (d == 0).mean(),
                     "mergegen_gap_larger": (d < 0).mean(),
                     "rank_biserial": paired_rank_biserial(g_sbcr, g_mg), "p": p})
    t = pd.DataFrame(rows)
    t["p_holm"] = holm(t.p)
    t["detectable"] = t.p_holm < 0.05
    t["ci_excludes_zero"] = (t.ci_low > 0) | (t.ci_high < 0)
    return t


def check_against_comparison(t, root):
    """The eight means must be those `compare_approaches.py` wrote to `comparison.csv`.

    The own configuration is in analysis `rq1_rq2`, the other in `rq3`. Valid only when
    `comparison.csv` was written with the same SBCR seeds as this run.
    """
    c = pd.read_csv(os.path.join(root, "comparison.csv"))
    c = c[c.arm == ARM].set_index(["analysis", "dataset"])
    worst = 0.0
    for r in t.itertuples():
        column = "sbcr" if r.approach == "SBCR" else "mergegen"
        for analysis, mean in (("rq1_rq2", r.own_mean), ("rq3", r.other_mean)):
            worst = max(worst, abs(c.loc[(analysis, r.test_set), column] - mean))
    if worst > COMPARISON_TOLERANCE:
        raise RuntimeError(f"means differ from comparison.csv by up to {worst:.3g}")
    return worst


def inputs(root, seeds):
    """Files the run reads, for the hashes in the JSON."""
    files = [os.path.join(root, "sbcr_similarities.csv")]
    for target in sum(SBCR_TARGETS.values(), ()):
        for seed in seeds:
            folder = os.path.join(root, "sbcr", f"eval_{target}_{ARM}_s{seed}", "RESULTS")
            files += sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".xlsx"))
    for test_set in SBCR_TARGETS:
        for model in (test_set, OTHER[test_set]):
            files.append(os.path.join(root, "mergeGen", "JIT", f"{test_set}_{ARM}", f"model_{model}_{ARM}",
                                      "similarities.csv"))
        files.append(os.path.join(root, "data", f"{split_key(test_set, ARM)}_testing.json"))
    return files


def show(t, cols):
    pd.set_option("display.width", 200)
    print(t[cols].to_string(index=False, float_format=lambda x: f"{x:.4g}"))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--sbcr-seeds", required=True, help="SBCR seeds, separated by commas")
    p.add_argument("--out", required=True)
    p.add_argument("--check-against-comparison", action="store_true",
                   help="check the eight means against the root's comparison.csv (same seeds only)")
    args = p.parse_args()
    root = os.path.expanduser(args.root)
    seeds = sorted({s.strip() for s in args.sbcr_seeds.split(",") if s.strip()})
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)

    evaluated = evaluated_sets(root)
    sbcr = sbcr_by_target(load_sbcr_similarities(root, seeds=seeds), seeds, evaluated)
    mergegen = mergegen_by_model(load_mergegen(root, evaluated), evaluated)
    t = gaps(sbcr, mergegen)
    show(t, ["approach", "test_set", "n", "own_mean", "other_mean", "gap", "ci_low", "ci_high", "own_closer", "tie",
             "other_closer", "rank_biserial", "p", "p_holm", "detectable", "ci_excludes_zero"])
    diff = gap_difference(sbcr, mergegen)
    print("\n--- SBCR's gap minus MergeGen's gap ---")
    show(diff, ["test_set", "n", "sbcr_gap", "mergegen_gap", "difference", "ci_low", "ci_high", "sbcr_gap_larger",
                "equal", "mergegen_gap_larger", "rank_biserial", "p", "p_holm", "detectable", "ci_excludes_zero"])
    for r in diff.itertuples():
        expected = t.set_index(["approach", "test_set"]).gap
        if abs(r.difference - (expected[("SBCR", r.test_set)] - expected[("MergeGen", r.test_set)])) > 1e-12:
            raise RuntimeError(f"the difference of gaps on {r.test_set} is not the difference of the two mean gaps")

    worst = None
    if args.check_against_comparison:
        worst = check_against_comparison(t, root)
        print(f"\nmeans match comparison.csv, largest difference {worst:.3g}")

    name = f"rq3_gaps_s{'-'.join(seeds)}"
    t.to_csv(os.path.join(out, f"{name}.csv"), index=False)
    diff.to_csv(os.path.join(out, f"rq3_gap_difference_s{'-'.join(seeds)}.csv"), index=False)
    commit = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    # the code the run imports: this folder and `chronological_effects.py`, which gives `holm`
    dirty = bool(subprocess.run(["git", "-C", HERE, "status", "--porcelain", "--", HERE, CHRONO],
                                capture_output=True, text=True).stdout.strip())
    meta = {"root": root, "sbcr_seeds": seeds, "similarity": SIM, "commit": commit, "uncommitted_changes": dirty,
            "interval": "mean +- 1.96 sd / sqrt(n), normal approximation, not adjusted",
            "test": "scipy.stats.wilcoxon, two-sided, defaults", "correction": "Holm over the four tests, and over the two tests of the difference of gaps",
            "comparison_largest_difference": worst,
            "inputs": {os.path.relpath(f, root): sha256(f) for f in inputs(root, seeds)}}
    with open(os.path.join(out, f"{name}.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nwritten to {out}/{name}.csv, .json and rq3_gap_difference_s{'-'.join(seeds)}.csv")


if __name__ == "__main__":
    main()
