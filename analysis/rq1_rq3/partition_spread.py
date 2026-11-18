#!/usr/bin/env python3
"""Spread across the three partitions of the merge-grouped design of the SBCR - MergeGen difference.

In each partition, the paired comparison of the two approaches on the same conflicts (as in
`compare_approaches.py`), for each dataset (RQ1 and RQ2) and for the two crossed evaluations of
RQ3, and the spread of the difference across partitions. SBCR enters with seed 3022024 in every
partition. When a root has more than one seed, the mean over its seeds comes out in rows of its
own (`variant = mean_<n>_seeds`) and does not enter the spread.

Inputs: the roots of the partitions (`--partition N=ROOT`, read only).
Outputs, in `--out`: `comparison_per_partition.csv` and `partition_spread.csv`.

    python analysis/rq1_rq3/partition_spread.py --partition 1=<root 1> --partition 2=<root 2> \
        --partition 3=<root 3> --out <dir>
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

ARM = "mg"
SEED = "3022024"


def comparisons(root, sb, seeds):
    """RQ1/RQ2 and RQ3 of the mg arm of a root, with SBCR averaged over `seeds`."""
    evaluated = evaluated_sets(root)
    sb = sb[(sb.arm == ARM) & (sb.partition == ARM) & sb.seed.isin(seeds)]
    missing = set(seeds) - set(sb.seed)
    if missing:
        raise ValueError(f"{root}: no SBCR evaluation for seeds {sorted(missing)}")
    mg = load_mergegen(root, evaluated)
    mg = mg[mg.arm == ARM]

    j, j3 = paired_frames(sb, mg)
    return pd.concat([paired_comparison(j, "rq1_rq2"), paired_comparison(j3, "rq3")], ignore_index=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--partition", action="append", required=True, metavar="N=ROOT")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    partitions = dict(x.split("=", 1) for x in args.partition)
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)

    rows = []
    for n, root in sorted(partitions.items()):
        root = os.path.expanduser(root)
        sb = load_sbcr_similarities(root)
        t = comparisons(root, sb, [SEED])
        t["partition"], t["variant"] = int(n), f"seed_{SEED}"
        rows.append(t)
        seeds = sorted(sb[sb.arm == ARM].seed.unique())
        if len(seeds) > 1:
            t = comparisons(root, sb, seeds)
            t["partition"], t["variant"] = int(n), f"mean_{len(seeds)}_seeds"
            rows.append(t)
    everything = pd.concat(rows, ignore_index=True)
    everything = everything[["analysis", "dataset", "partition", "variant", "n", "out_of_limits", "sbcr",
                             "mergegen", "difference", "sbcr_wins", "tie", "mergegen_wins",
                             "rank_biserial", "p"]]
    everything.to_csv(os.path.join(out, "comparison_per_partition.csv"), index=False)

    base = everything[everything.variant == f"seed_{SEED}"]
    spread = []
    for (analysis, dataset), g in base.groupby(["analysis", "dataset"], sort=False):
        g = g.set_index("partition").sort_index()
        row = {"analysis": analysis, "dataset": dataset, "partitions": len(g)}
        for k, v in g.difference.items():
            row[f"difference_p{k}"] = v
        for column in ("difference", "sbcr", "mergegen"):
            row[f"{column}_mean"] = g[column].mean()
            row[f"{column}_sd"] = g[column].std(ddof=1)
        row["difference_min"], row["difference_max"] = g.difference.min(), g.difference.max()
        row["difference_amplitude"] = g.difference.max() - g.difference.min()
        row["p_max"] = g.p.max()
        row["mergegen_wins_min"], row["mergegen_wins_max"] = g.mergegen_wins.min(), g.mergegen_wins.max()
        spread.append(row)
    spread = pd.DataFrame(spread)
    spread.to_csv(os.path.join(out, "partition_spread.csv"), index=False)

    pd.set_option("display.width", 200)
    print("=== SBCR − MergeGen difference per partition (SBCR with seed 3022024) ===")
    print(base.pivot_table(index=["analysis", "dataset"], columns="partition", values="difference",
                           sort=False).round(4).to_string())
    print("\n=== spread across partitions ===")
    print(spread[["analysis", "dataset", "difference_mean", "difference_sd", "difference_min",
                  "difference_max", "difference_amplitude", "p_max"]].round(4).to_string(index=False))
    others = everything[everything.variant != f"seed_{SEED}"]
    if len(others):
        print("\n=== reference: mean over seeds, where there is more than one ===")
        print(others[["analysis", "dataset", "partition", "variant", "difference"]].round(4).to_string(index=False))
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
