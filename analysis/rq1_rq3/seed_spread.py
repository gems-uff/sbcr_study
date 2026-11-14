#!/usr/bin/env python3
"""SBCR against MergeGen with each SBCR seed, and with their mean.

The paired comparison of `compare_approaches.py`, run once per seed of a root, so that the range
of each number across seeds can be read beside the value of seed 3022024 and beside the mean of
the seeds. Out-of-limits conflicts score 0 for SBCR, and only the main analyses (`rq1_rq2`,
`rq3`) are computed. It also prints the total time of each evaluation over that of seed 3022024
on the same conflicts, since SBCR's search is bounded by wall-clock time and a slower run
completes fewer iterations.

Input: a root with several SBCR seeds (`--root`).
Outputs, in the root: `comparison_per_seed.csv` (one row per seed, analysis and dataset) and
`seed_summary.csv` (seed 3022024, the mean of the seeds, and the lowest and highest value per
analysis, dataset and measure).

    python analysis/rq1_rq3/seed_spread.py --root <root>
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from compare_approaches import evaluated_sets, load_mergegen, paired_comparison, paired_frames  # noqa: E402
from sbcr_scores import load_sbcr_similarities  # noqa: E402

REFERENCE = "3022024"
MEASURES = ["sbcr", "difference", "sbcr_wins", "tie", "mergegen_wins", "rank_biserial", "p",
            "sbcr_sd", "sbcr_median", "sbcr_exact"]


def comparisons(sb, mg, label):
    j, j3 = paired_frames(sb, mg)
    return pd.concat([paired_comparison(j, "rq1_rq2"), paired_comparison(j3, "rq3")],
                     ignore_index=True).assign(seed=label)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    root = os.path.expanduser(p.parse_args().root)

    sb = load_sbcr_similarities(root)
    sb = sb[sb.partition == sb.arm]
    mg = load_mergegen(root, evaluated_sets(root))
    seeds = sorted(sb.seed.unique())
    print(f"seeds: {', '.join(seeds)}")

    per_seed = pd.concat([comparisons(sb[sb.seed == s], mg, s) for s in seeds], ignore_index=True)
    per_seed.to_csv(f"{root}/comparison_per_seed.csv", index=False)
    mean5 = comparisons(sb, mg, "mean")

    keys = ["analysis", "dataset"]
    long = per_seed.melt(id_vars=keys + ["seed"], value_vars=MEASURES, var_name="measure")
    span = long.groupby(keys + ["measure"]).value.agg(lowest="min", highest="max").reset_index()
    ref = long[long.seed == REFERENCE].drop(columns="seed").rename(columns={"value": REFERENCE})
    avg = (mean5.melt(id_vars=keys + ["seed"], value_vars=MEASURES, var_name="measure")
           .drop(columns="seed").rename(columns={"value": "mean_of_five"}))
    summary = ref.merge(avg, on=keys + ["measure"]).merge(span, on=keys + ["measure"])
    summary["mean_minus_reference"] = summary.mean_of_five - summary[REFERENCE]
    summary.to_csv(f"{root}/seed_summary.csv", index=False)

    for measure in MEASURES:
        t = summary[summary.measure == measure].drop(columns="measure")
        fmt = (lambda x: f"{x:.1e}") if measure == "p" else (lambda x: f"{x:.4f}")
        print(f"\n--- {measure} ---")
        print(t.to_string(index=False, formatters={c: fmt for c in t.columns if c not in keys}))

    ok = sb[sb.status == "ok"]
    ref_time = ok[ok.seed == REFERENCE][["target", "chunk_id", "time"]]
    both = ok[ok.seed != REFERENCE].merge(ref_time, on=["target", "chunk_id"], suffixes=("", "_ref"))
    ratio = both.groupby(["target", "seed"])[["time", "time_ref"]].sum()
    ratio = (ratio.time / ratio.time_ref).unstack()
    print("\n--- time per evaluation over that of seed 3022024, same conflicts ---")
    print(ratio.round(2).to_string())
    print(f"lowest {ratio.min().min():.2f}, highest {ratio.max().max():.2f}")
    print(f"\nwritten to {root}/comparison_per_seed.csv and {root}/seed_summary.csv")


if __name__ == "__main__":
    main()
