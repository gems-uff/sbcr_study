#!/usr/bin/env python3
"""Merge commits shared by a test partition and a training partition under another project name.

The merge-grouped split groups chunks by the pair (normalized project, commit), so two chunks
with the same commit hash under two project names (a fork, a renamed repository) can fall in
different partitions. The script counts, by the hash of the merge commit alone, how many chunks
of a test partition have their hash in a training partition, in each root, and lists the pairs
of project names when there is any. Across the two Java datasets (the test of one, the training
of the other) is the exposure of RQ3; within each dataset, that of RQ1 and RQ2. Two test sets
are counted: the whole test partition, and the evaluated test, the file SBCR reads.

Inputs: the datasets (`--data-root`) and the roots (`--root name=path`, once per root).
Outputs, in `--out`: `shared_commits_counts.csv` and, when there is a hit, `shared_commits_pairs.csv`.

    python analysis/datasets/shared_commits.py --data-root <data> --root 1=<root 1> --root 2=<root 2> --out <dir>
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "preparation"))
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from survey import LANGUAGES, load_dataset1, load_dataset2  # noqa: E402
from sbcr_scores import sbcr_chunk_ids  # noqa: E402

DATASETS = ["dataset1"] + [f"dataset2_{lang}" for lang in LANGUAGES]
# (test of, training of): across the two Java datasets (RQ3), then within each dataset (RQ1, RQ2)
PAIRS = [("dataset1", "dataset2_Java"), ("dataset2_Java", "dataset1")] + [(ds, ds) for ds in DATASETS]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-root", required=True)
    p.add_argument("--root", action="append", required=True, help="name=path, once per root")
    p.add_argument("--arm", default="mg")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)
    data_root = os.path.expanduser(args.data_root)

    meta = {}
    for ds in DATASETS:
        df = (load_dataset1(data_root) if ds == "dataset1"
              else load_dataset2(data_root, ds.removeprefix("dataset2_")))
        df = df[["chunk_id", "project", "commit"]].copy()
        df["commit"] = df["commit"].astype(str).str.strip().str.lower()
        meta[ds] = df

    counts, pairs = [], []
    for spec in args.root:
        name, root = spec.split("=", 1)
        root = os.path.expanduser(root)
        part = {}
        for ds in meta:
            s = pd.read_csv(f"{root}/splits/{args.arm}/{ds}.csv", dtype={"chunk_id": str})
            part[ds] = meta[ds].merge(s[["chunk_id", "partition"]], on="chunk_id", how="inner")
        for test_ds, train_ds in PAIRS:
            train = part[train_ds][part[train_ds].partition == "train"]
            hashes = set(train["commit"])
            test = part[test_ds][part[test_ds].partition == "test"]
            evaluated = sbcr_chunk_ids(root, test_ds, args.arm)
            for label, t in (("whole test", test), ("evaluated test", test[test.chunk_id.isin(evaluated)])):
                hit = t[t["commit"].isin(hashes)]
                counts.append({"root": name, "test_of": test_ds, "training_of": train_ds, "test_set": label,
                               "test_chunks": len(t), "chunks_with_hash_in_training": len(hit),
                               "merge_commits": hit["commit"].nunique()})
                if label == "whole test" and len(hit):
                    j = hit[["commit", "project"]].drop_duplicates().merge(
                        train[["commit", "project"]].drop_duplicates(), on="commit", suffixes=("_test", "_training"))
                    if (j.project_test == j.project_training).any():
                        raise RuntimeError(f"{name}: a hit under the same project name, {test_ds} / {train_ds}")
                    j["root"], j["test_of"], j["training_of"] = name, test_ds, train_ds
                    j["evaluated"] = j["commit"].isin(set(t[t.chunk_id.isin(evaluated)]["commit"]))
                    pairs.append(j)

    counts = pd.DataFrame(counts)
    counts.to_csv(f"{out}/shared_commits_counts.csv", index=False)
    print(counts.to_string(index=False))
    if pairs:
        pairs = pd.concat(pairs, ignore_index=True)
        pairs.to_csv(f"{out}/shared_commits_pairs.csv", index=False)
        print("\n=== pairs of project names ===")
        print(pairs.to_string(index=False))
    else:
        print("\nno shared hash in any root")


if __name__ == "__main__":
    main()
