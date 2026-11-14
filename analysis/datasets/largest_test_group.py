#!/usr/bin/env python3
"""Largest group that reaches the test, and the share of chunks in groups larger than it.

Two readings: per universe (Dataset1 and Dataset2_Java together, C#, JavaScript, TypeScript), a
group's size is its number of chunks in the universe and the share is over the chunks of the
universe; per dataset, the same within one dataset.

Input: a folder with one subfolder of split files per arm (`--splits`).
Output: the table, in `--out` and on the standard output.

    python analysis/datasets/largest_test_group.py --splits <root>/splits --arms mg,pd --out <file.csv>
"""
import argparse
import os

import pandas as pd

UNIVERSES = {
    "dataset1+dataset2_Java": ["dataset1", "dataset2_Java"],
    "dataset2_CSharp": ["dataset2_CSharp"],
    "dataset2_JavaScript": ["dataset2_JavaScript"],
    "dataset2_TypeScript": ["dataset2_TypeScript"],
}


def measure(df):
    size = df.groupby("group").size()
    in_test = set(df.loc[df.partition == "test", "group"])
    largest = int(size[size.index.isin(in_test)].max())
    above = size[size > largest]
    return largest, int(above.sum()), len(df), int(len(above))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--splits", required=True)
    p.add_argument("--arms", default="mg,pd")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    splits = os.path.expanduser(args.splits)

    rows = []
    for arm in args.arms.split(","):
        for universe, datasets in UNIVERSES.items():
            parts = {ds: pd.read_csv(f"{splits}/{arm}/{ds}.csv", dtype={"chunk_id": str}) for ds in datasets}
            readings = [("universe", universe, pd.concat(parts.values(), ignore_index=True))]
            readings += [("dataset", ds, d) for ds, d in parts.items()]
            for unit, name, df in readings:
                largest, above, total, groups = measure(df)
                rows.append({"arm": arm, "unit": unit, "set": name, "chunks": total,
                             "largest_test_group": largest, "groups_larger": groups,
                             "chunks_in_larger_groups": above, "share_in_larger_groups": round(100 * above / total, 1)})
    out = pd.DataFrame(rows)
    out.to_csv(os.path.expanduser(args.out), index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
