#!/usr/bin/env python3
"""Partition sizes of one root and the combination subset of each partition.

Counts chunks and groups per partition from `splits/<arm>/<dataset>.csv`, and takes the
duplicates removed from `splits/summary.csv` (`preparation/make_splits.py`). The combination
subset of each partition is what SBCR is tuned and evaluated on (`preparation/prepare_sbcr.py`);
Dataset1 enters whole. The script rebuilds every subset with the filter of
`preparation/combination.py` and stops if a file differs from it. For Dataset1 it reports how
many chunks the filter would keep, and the strategy of each chunk it would drop.

Input: the root (`--root`). Output: `<root>/partition_sizes.csv`, and the table as Markdown.

    python analysis/datasets/partition_sizes.py --root <root> [--arm mg]
"""
import argparse
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "preparation"))
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from combination import strategy as resolution_strategy  # noqa: E402
from sbcr_scores import sbcr_chunk_ids, sbcr_data_file  # noqa: E402
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
PARTITIONS = {"train": "training", "validation": "validation", "test": "testing"}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--arm", default="mg")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))

    summary = pd.read_csv(f"{root}/splits/summary.csv")
    summary = summary[summary.arm == args.arm].set_index("dataset")
    rows, dropped = [], []
    for name in DATASETS:
        data = json.load(open(f"{root}/data/{name}.json"))
        idx = {str(c): i for i, c in enumerate(data["chunk_id"])}
        a = pd.read_csv(f"{root}/splits/{args.arm}/{name}.csv", dtype={"chunk_id": str})
        if a.chunk_id.duplicated().any() or not set(a.chunk_id) <= set(idx):
            raise SystemExit(f"{name}: the assignment has repeated chunks or chunks missing from the dataset")
        if a.groupby("group").partition.nunique().max() > 1:
            raise SystemExit(f"{name}: a group is split across partitions")
        if summary.loc[name, "chunks"] != len(a):
            raise SystemExit(f"{name}: splits/summary.csv and the assignment differ in the number of chunks")
        row = {"dataset": name, "chunks": len(a), "groups": a.group.nunique(),
               "duplicates_removed": int(summary.loc[name, "duplicates_removed"])}
        for part, suffix in PARTITIONS.items():
            ids = a[a.partition == part].chunk_id
            strategy = {c: resolution_strategy(data["all_raw_a"][idx[c]], data["all_raw_b"][idx[c]],
                                               data["all_raw_res"][idx[c]]) for c in ids}
            comb = {c for c, k in strategy.items() if k == "Combination"}
            if name == "dataset1":
                dropped += [(part, c, k) for c, k in sorted(strategy.items()) if k != "Combination"]
            file = sbcr_data_file(root, name, args.arm, suffix)
            used = sbcr_chunk_ids(root, name, args.arm, suffix)
            expected = set(ids) if name == "dataset1" else comb
            if used != expected:
                raise SystemExit(f"{name}/{part}: {file} differs from the rebuilt subset "
                                 f"({len(used - expected)} only in the file, {len(expected - used)} missing)")
            row.update({part: len(ids), f"{part}_groups": a[a.partition == part].group.nunique(),
                        f"{part}_combination": len(used), f"{part}_combination_filter": len(comb)})
        rows.append(row)

    table = pd.DataFrame(rows)
    table.to_csv(f"{root}/partition_sizes.csv", index=False)
    print("| dataset | chunks | duplicates removed | groups | training | validation | test | combination, training "
          "| combination, validation | combination, test |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in table.itertuples():
        print(f"| {r.dataset} | {r.chunks:,} | {r.duplicates_removed:,} | {r.groups:,} "
              f"| {r.train:,} | {r.validation:,} | {r.test:,} "
              f"| {r.train_combination:,} | {r.validation_combination:,} | {r.test_combination:,} |")
    print("\nGroups per partition, and chunks the combination filter keeps (Dataset1 enters whole):")
    for r in table.itertuples():
        print(f"  {r.dataset}: groups {r.train_groups:,} / {r.validation_groups:,} / {r.test_groups:,}; "
              f"filter keeps {r.train_combination_filter:,} / {r.validation_combination_filter:,} "
              f"/ {r.test_combination_filter:,}")
    print("\nDataset1 chunks the combination filter would drop (partition, chunk, strategy):")
    for d in dropped:
        print("  ", d)


if __name__ == "__main__":
    main()
