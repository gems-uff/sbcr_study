#!/usr/bin/env python3
"""Share of each dataset's chunks in groups above the cap of the merge-grouped split.

With the cap rule of `preparation/make_splits.py`, a group that alone would take more than
`--cap` of the test partition of a dataset (10% of its chunks) goes to training before the draw,
so its chunks never reach the test. The share depends on the sizes of the groups and not on the
seed of the draw. The script recomputes it from the split files of a root, as `assign_cap`
measures it, and checks that every such group is in training.

Input: `<root>/splits/mg/<dataset>.csv` (`--splits <root>/splits`).
Output: one row per dataset, on the standard output and in `--out` when given.

    python analysis/datasets/cap_share.py --splits <root>/splits [--cap 0.05] [--out <file.csv>]
"""
import argparse
import os

import pandas as pd

UNIVERSES = [["dataset1", "dataset2_Java"], ["dataset2_CSharp"], ["dataset2_JavaScript"], ["dataset2_TypeScript"]]
TEST_SHARE = 0.1


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--splits", required=True, help="the splits folder of a root")
    p.add_argument("--arm", default="mg")
    p.add_argument("--cap", type=float, default=0.05)
    p.add_argument("--out", help="CSV to write the table to")
    args = p.parse_args()
    splits = os.path.expanduser(args.splits)

    rows = []
    for universe in UNIVERSES:
        df = pd.concat([pd.read_csv(f"{splits}/{args.arm}/{ds}.csv", dtype={"chunk_id": str}).assign(dataset=ds)
                        for ds in universe], ignore_index=True)
        per_dataset = df.groupby(["group", "dataset"]).size().unstack(fill_value=0)
        test_per_dataset = df.dataset.value_counts() * TEST_SHARE
        share = (per_dataset / test_per_dataset[per_dataset.columns]).max(axis=1)
        large = set(share[share > args.cap].index)
        outside_train = df[df.group.isin(large) & (df.partition != "train")]
        if len(outside_train):
            raise SystemExit(f"{'+'.join(universe)}: {len(outside_train)} chunks of groups above the cap "
                             "are not in training")
        for ds in universe:
            d = df[df.dataset == ds]
            above = d[d.group.isin(large)]
            rows.append({"dataset": ds, "chunks": len(d), "groups_above_cap": above.group.nunique(),
                         "chunks_above_cap": len(above), "pct_above_cap": round(100 * len(above) / len(d), 1)})
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    if args.out:
        table.to_csv(os.path.expanduser(args.out), index=False)


if __name__ == "__main__":
    main()
