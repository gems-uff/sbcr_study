#!/usr/bin/env python3
"""Counts of the paired conflicts in which SBCR is faster than MergeGen, slower, and tied.

The shares of `times_per_language.csv` times the number of paired conflicts, for one dataset of
the combination population.

Input: `times_per_language.csv` of a root (`times_per_language.py`).
Output: one line, `n faster slower ties`, on the standard output.

    python analysis/rq1_rq3/faster_slower_counts.py <root>/times_per_language.csv [--dataset dataset1]
"""
import argparse

import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("table", help="times_per_language.csv")
    p.add_argument("--dataset", default="dataset1")
    args = p.parse_args()
    t = pd.read_csv(args.table)
    d = t[(t.dataset == args.dataset) & (t.population == "combination")].iloc[0]
    n = int(d.paired_n)
    print(n, round(d.sbcr_faster_share * n), round(d.sbcr_slower_share * n),
          round((1 - d.sbcr_faster_share - d.sbcr_slower_share) * n))


if __name__ == "__main__":
    main()
