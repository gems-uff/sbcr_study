#!/usr/bin/env python3
"""Overlap between the test partitions of the three splits of the merge-grouped design.

For each dataset, the share of the test chunks of one split that are also in the test of
another, for each ordered pair of splits, and the share that are in the test of all three.
Independent random draws of 10% would give about 10% and 1%.

Inputs: the roots of the splits (`--partition N=ROOT`), read from `splits/mg/<dataset>.csv`.
Output: one row per dataset, on the standard output and in `--out` when given.

    python analysis/datasets/test_overlap.py --partition 1=<root 1> --partition 2=<root 2> \
        --partition 3=<root 3> [--out <file.csv>]
"""
import argparse
import itertools
import os

import pandas as pd

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--partition", action="append", required=True, metavar="N=ROOT")
    p.add_argument("--arm", default="mg")
    p.add_argument("--out", help="CSV to write the table to")
    args = p.parse_args()
    roots = dict(sorted(x.split("=", 1) for x in args.partition))

    rows = []
    for ds in DATASETS:
        tests = {}
        for n, root in roots.items():
            a = pd.read_csv(f"{os.path.expanduser(root)}/splits/{args.arm}/{ds}.csv", dtype={"chunk_id": str})
            tests[n] = set(a[a.partition == "test"].chunk_id)
        pairs = {f"{i}_in_{j}": len(tests[i] & tests[j]) / len(tests[i])
                 for i, j in itertools.permutations(tests, 2)}
        common = set.intersection(*tests.values())
        in_all = {n: len(common) / len(t) for n, t in tests.items()}
        rows.append({"dataset": ds, **{f"test_{n}": len(t) for n, t in tests.items()},
                     "in_all": len(common),
                     "pair_min_pct": round(100 * min(pairs.values()), 1),
                     "pair_max_pct": round(100 * max(pairs.values()), 1),
                     "all_min_pct": round(100 * min(in_all.values()), 1),
                     "all_max_pct": round(100 * max(in_all.values()), 1),
                     **{f"pct_{k}": round(100 * v, 1) for k, v in pairs.items()}})
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    if args.out:
        table.to_csv(os.path.expanduser(args.out), index=False)


if __name__ == "__main__":
    main()
