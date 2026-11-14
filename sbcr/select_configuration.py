#!/usr/bin/env python3
"""Applies the selection rule to the SBCR tuning results: the configuration of each run.

Rule: the highest mean similarity; within 0.005 of it, the lowest mean time. The script also
reports the four metrics of the tuning table (mean similarity, mean time, Top-1 and mean
ranking of each configuration).

Input: `<root>/sbcr/tuning_*/RESULTS/*.xlsx` (`sbcr_tuning.py`).
Output: `<root>/chosen_configurations.csv`, one row per tuning run.

    python sbcr/select_configuration.py --root <root> [--arm mg]
"""
import argparse
import glob
import os
import re

import pandas as pd

MARGIN = 0.005


def metrics(df):
    """Four metrics per configuration."""
    df = df[df.status == "ok"].copy()
    df["config"] = (df.maximum_neighbors.astype(int).astype(str) + ", "
                    + df.max_iterations_without_improvement.astype(int).astype(str) + ", "
                    + df.ils_timeout.astype(int).astype(str))
    # rank of each configuration within each conflict, 1 = best
    df["ranking"] = df.groupby("chunk_id").solution_sim_lcs.rank(ascending=False, method="min")
    top1 = df[df.ranking == 1].groupby("config").chunk_id.nunique()
    r = df.groupby("config").agg(
        mean_similarity=("solution_sim_lcs", "mean"),
        mean_time=("time_seconds", "mean"),
        mean_ranking=("ranking", "mean"),
        conflicts=("chunk_id", "nunique"),
    )
    r["top1"] = top1.reindex(r.index).fillna(0).astype(int)
    return r.sort_values("mean_similarity", ascending=False)


def choose(r):
    """The highest mean similarity; within the margin, the lowest mean time."""
    best = r.mean_similarity.max()
    tied = r[r.mean_similarity >= best - MARGIN]
    return tied.mean_time.idxmin(), tied


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--arm", default=None, help="only this arm; all arms without it")
    args = p.parse_args()
    root = os.path.expanduser(args.root)

    rows = []
    for file in sorted(glob.glob(f"{root}/sbcr/tuning_*/RESULTS/*.xlsx")):
        label = os.path.basename(os.path.dirname(os.path.dirname(file))).replace("tuning_", "")
        arm = re.search(r"_(control|mg|pd)$", label)
        arm = arm.group(1) if arm else "?"
        if args.arm and arm != args.arm:
            continue
        r = metrics(pd.read_excel(file))
        chosen, tied = choose(r)
        print(f"=== {label} ===")
        print(r.head(5).round(4).to_string())
        print(f"  tied within {MARGIN}: {len(tied)}")
        print(f"  CHOSEN: ({chosen})  "
              f"sim={r.loc[chosen].mean_similarity:.4f}  "
              f"time={r.loc[chosen].mean_time:.2f}s\n")
        rows.append({"run": label, "arm": arm, "configuration": chosen,
                     "mean_similarity": r.loc[chosen].mean_similarity,
                     "mean_time": r.loc[chosen].mean_time,
                     "top1": r.loc[chosen].top1,
                     "mean_ranking": r.loc[chosen].mean_ranking,
                     "tied": len(tied)})
    if rows:
        t = pd.DataFrame(rows)
        t.to_csv(f"{root}/chosen_configurations.csv", index=False)
        print(t.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
