#!/usr/bin/env python3
"""Writes the partitions SBCR reads, for each arm.

SBCR reads `../data/{DATASET}_training.json` when tuning and `../data/{DATASET}_testing.json`
when evaluating. For Dataset2, `{DATASET}` ends in `_combination`, since only the conflicts
resolved by combination are in the scope of the study. Dataset1 holds only combination
conflicts and is not filtered.

Inputs: `<root>/data/{dataset}.json` and `<root>/data/split_{dataset}_{arm}.csv` (`prepare_data.py`).
Outputs: `<root>/data/{dataset}_{arm}[_combination]_{training,validation,testing}.json`.

    python preparation/prepare_sbcr.py --root <root> --arms mg
    python preparation/prepare_sbcr.py --check --data-root <data>   # filter against the submitted partitions
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from combination import strategy  # noqa: E402
from survey import LANGUAGES  # noqa: E402

ARMS = ("random", "mg", "pd")
PARTITIONS = (("train", "training"), ("validation", "validation"), ("test", "testing"))


def load(path):
    d = pd.DataFrame(json.load(open(path)))
    if "chunk_id" not in d.columns:
        d["chunk_id"] = d.merge_id.astype(str) + "-" + d.chunk_number.astype(str)
    d["chunk_id"] = d.chunk_id.astype(str)
    return d


def write(df, path):
    columns = ["chunk_id", "all_raw_a", "all_raw_b", "all_raw_res", "all_raw_base"]
    with open(path, "w") as f:
        json.dump({c: df[c].tolist() for c in columns}, f, indent=4)
    return len(df)


def check(source):
    """The filter must reproduce the combination partitions of the submitted version."""
    for language in LANGUAGES:
        base = load(os.path.join(source, f"dataset2_{language}_testing.json"))
        expected = set(map(str, json.load(open(
            os.path.join(source, f"dataset2_{language}_combination_testing.json")))["chunk_id"]))
        obtained = set(base[[strategy(a, b, r) == "Combination"
                             for a, b, r in zip(base.all_raw_a, base.all_raw_b, base.all_raw_res)]].chunk_id)
        verdict = "equal" if obtained == expected else f"DIFFERS (+{len(obtained - expected)} / -{len(expected - obtained)})"
        print(f"  dataset2_{language}: expected {len(expected)}, obtained {len(obtained)} -> {verdict}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", help="experiment root")
    p.add_argument("--check", action="store_true",
                   help="only check the combination filter against the partitions of the submitted version")
    p.add_argument("--data-root", help="folder with the datasets of the submitted version, for --check")
    p.add_argument("--arms", default=",".join(ARMS), help="arms present in data/, comma-separated")
    args = p.parse_args()
    arms = [a for a in args.arms.split(",") if a]

    if args.check:
        if not args.data_root:
            p.error("--check needs --data-root")
        print("checking the combination filter against the partitions of the submitted version:")
        check(os.path.expanduser(args.data_root))
        return
    if not args.root:
        p.error("--root is required")

    data = os.path.join(os.path.expanduser(args.root), "data")
    for name in ["dataset1"] + [f"dataset2_{language}" for language in LANGUAGES]:
        df = load(os.path.join(data, f"{name}.json"))
        if name != "dataset1":
            mask = [strategy(a, b, r) == "Combination" for a, b, r in zip(df.all_raw_a, df.all_raw_b, df.all_raw_res)]
            combination = df[mask]
        else:
            combination = df
        for arm in arms:
            assignment = pd.read_csv(os.path.join(data, f"split_{name}_{arm}.csv"), dtype={"chunk_id": str})
            per_chunk = dict(zip(assignment.chunk_id, assignment.partition))
            label = f"{name}_{arm}" if name == "dataset1" else f"{name}_{arm}_combination"
            counts = []
            for partition, suffix in PARTITIONS:
                part = combination[combination.chunk_id.map(per_chunk) == partition]
                counts.append(write(part, os.path.join(data, f"{label}_{suffix}.json")))
            print(f"{label}: train {counts[0]}, validation {counts[1]}, test {counts[2]}", flush=True)


if __name__ == "__main__":
    main()
