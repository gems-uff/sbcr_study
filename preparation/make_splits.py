#!/usr/bin/env python3
"""Assigns each chunk to the train, validation or test partition, for each split design (arm).

Three arms, all on the deduplicated data:

- `control` random split at the level of the chunk;
- `mg`      merge-grouped: the chunks of a merge always fall in the same partition;
- `pd`      project-disjoint: the chunks of a project always fall in the same partition.

In `mg` and `pd` a group is a connected component, not a single key: identical conflicts
across datasets also join groups, so that the cross-dataset evaluation of RQ3 does not see
in the test a conflict seen in training. For the same reason Dataset1 and Dataset2_Java are
split together, since they share projects, commits and identical conflicts.

Inputs: the datasets in `--data-root` (see `survey.py`).
Outputs, in `--out`: `<arm>/<dataset>.csv` (chunk_id, partition, group), `summary.csv`
(sizes and the largest group per dataset and arm) and `contamination.csv` (test chunks that
share content, merge or project with training, the acceptance test).

    python preparation/make_splits.py --data-root <data> --out <root>/splits --seed <seed> \
        --arms mg --rule cap --cap 0.05
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from combination import is_combination  # noqa: E402
from survey import (  # noqa: E402
    LANGUAGES,
    SUBMITTED_SEED,
    UnionFind,
    load_dataset1,
    load_dataset2,
    text_hash,
    without_spaces,
)

ARMS = ("control", "mg", "pd")
RATIOS = (0.8, 0.1, 0.1)


def prepare(name, df):
    df = df.copy()
    df["dataset"] = name
    df["h_content_norm"] = [
        text_hash(without_spaces(b), without_spaces(a), without_spaces(bb), without_spaces(r))
        for b, a, bb, r in zip(df.all_raw_base, df.all_raw_a, df.all_raw_b, df.all_raw_res)
    ]
    # MergeGen trains on the whole dataset, but only the combination conflicts are
    # evaluated. Both sets must be split 80/10/10, so they are strata of the balance.
    df["stratum"] = df.dataset + "|" + [
        "combination" if is_combination(a, b, r) else "rest"
        for a, b, r in zip(df.all_raw_a, df.all_raw_b, df.all_raw_res)
    ]
    return df[["dataset", "stratum", "chunk_id", "project", "commit", "merge", "h_content_norm"]]


def deduplicate(df):
    """Removes the exact duplicates after normalization, keeping the first occurrence."""
    before = len(df)
    df = df.drop_duplicates(subset="h_content_norm", keep="first").reset_index(drop=True)
    return df, before - len(df)


def groups(df, arm):
    if arm == "control":
        return df.dataset + "|" + df.chunk_id
    uf = UnionFind()
    keys = ["merge", "h_content_norm"] if arm == "mg" else ["project", "commit", "h_content_norm"]
    # each chunk is a node, and each value of a key is an extra node that joins its chunks
    nodes = df.dataset + "|" + df.chunk_id
    for node in nodes:
        uf.find(node)
    for key in keys:
        for value, indices in df.groupby(key).indices.items():
            anchor = f"{key}::{value}"
            for i in indices:
                uf.union(nodes.iloc[i], anchor)
    return pd.Series([uf.find(n) for n in nodes], index=df.index)


def assign(df, group_column, seed):
    """Distributes whole groups 80/10/10 by chunk count, the largest groups first.

    Each group goes to the partition with the largest deficit, measured per stratum, so
    that each dataset and its combination subset are split 80/10/10. The seed breaks ties,
    since the groups are shuffled before the stable sort by size.
    """
    counts = df.groupby([group_column, "stratum"]).size().unstack(fill_value=0)
    order = counts.sum(axis=1).sample(frac=1, random_state=seed)
    counts = counts.loc[order.sort_values(ascending=False, kind="stable").index]

    totals = counts.sum()
    target = {p: totals * r for p, r in zip(("train", "validation", "test"), RATIOS)}
    current = {p: totals * 0 for p in target}

    destination = {}
    for group, row in counts.iterrows():
        weight = row / totals.replace(0, 1)
        chosen = max(target, key=lambda p: float((weight * (target[p] - current[p]) / totals.replace(0, 1)).sum()))
        destination[group] = chosen
        current[chosen] = current[chosen] + row
    return df[group_column].map(destination)


def assign_cap(df, group_column, seed, cap):
    """Distributes whole groups 80/10/10 in random order, with a cap per group.

    Each group goes to the partition with the largest deficit per stratum, as in `assign`,
    but in the order of the draw. A group that alone would take more than `cap` of the test
    partition of a dataset goes to training first.
    """
    counts = df.groupby([group_column, "stratum"]).size().unstack(fill_value=0)
    order = counts.sum(axis=1).sample(frac=1, random_state=seed)
    counts = counts.loc[order.index]

    per_dataset = df.groupby([group_column, "dataset"]).size().unstack(fill_value=0).loc[counts.index]
    test_per_dataset = df.dataset.value_counts() * RATIOS[2]
    share = (per_dataset / test_per_dataset[per_dataset.columns]).max(axis=1)
    large = share > cap

    totals = counts.sum()
    target = {p: totals * r for p, r in zip(("train", "validation", "test"), RATIOS)}
    current = {p: totals * 0 for p in target}

    destination = {}
    for group, row in counts[large].iterrows():
        destination[group] = "train"
        current["train"] = current["train"] + row
    for group, row in counts[~large].iterrows():
        weight = row / totals.replace(0, 1)
        chosen = max(target, key=lambda p: float((weight * (target[p] - current[p]) / totals.replace(0, 1)).sum()))
        destination[group] = chosen
        current[chosen] = current[chosen] + row
    return df[group_column].map(destination)


def summary(name, arm, df, removed):
    count = df.partition.value_counts()
    sizes = df.groupby("group").size()
    in_test = df[df.partition == "test"].groupby("group").size()
    return {
        "dataset": name,
        "arm": arm,
        "chunks": len(df),
        "duplicates_removed": removed,
        "groups": int(df.group.nunique()),
        "largest_group": int(sizes.max()),
        "train": int(count.get("train", 0)),
        "validation": int(count.get("validation", 0)),
        "test": int(count.get("test", 0)),
        "pct_train": round(100 * count.get("train", 0) / len(df), 1),
        "pct_validation": round(100 * count.get("validation", 0) / len(df), 1),
        "pct_test": round(100 * count.get("test", 0) / len(df), 1),
        "largest_group_test": int(in_test.max()) if len(in_test) else 0,
        "pct_largest_group_test": round(100 * in_test.max() / in_test.sum(), 2) if len(in_test) else 0.0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=SUBMITTED_SEED)
    p.add_argument("--rule", choices=("largest-first", "cap"), default="largest-first",
                   help="largest-first: the largest groups first; cap: random order with a cap per group")
    p.add_argument("--cap", type=float, default=0.05,
                   help="with --rule cap, the largest share of the test partition of a dataset one group may take")
    p.add_argument("--arms", default=",".join(ARMS),
                   help="arms to write, comma-separated; each arm is computed on its own")
    args = p.parse_args()
    arms = [a for a in args.arms.split(",") if a]
    if set(arms) - set(ARMS):
        p.error(f"unknown arm: {sorted(set(arms) - set(ARMS))}")
    root = os.path.expanduser(args.data_root)
    out = os.path.expanduser(args.out)

    print("loading data...", flush=True)
    raw = {"dataset1": prepare("dataset1", load_dataset1(root))}
    for language in LANGUAGES:
        name = f"dataset2_{language}"
        raw[name] = prepare(name, load_dataset2(root, language))

    # Dataset1 and Dataset2_Java are split together, since they share projects, commits
    # and identical conflicts. The three arms use the same data and the same deduplication.
    universes = [
        ["dataset1", "dataset2_Java"],
        ["dataset2_CSharp"],
        ["dataset2_JavaScript"],
        ["dataset2_TypeScript"],
    ]

    rows = []
    for arm in arms:
        for universe in universes:
            joint = pd.concat([raw[n] for n in universe], ignore_index=True)
            joint, removed_total = deduplicate(joint)
            joint["group"] = groups(joint, arm)
            if args.rule == "cap":
                joint["partition"] = assign_cap(joint, "group", args.seed, args.cap)
            else:
                joint["partition"] = assign(joint, "group", args.seed)

            for name in universe:
                part = joint[joint.dataset == name]
                destination = os.path.join(out, arm)
                os.makedirs(destination, exist_ok=True)
                part[["chunk_id", "partition", "group"]].to_csv(os.path.join(destination, f"{name}.csv"), index=False)
                removed = len(raw[name]) - len(part)
                r = summary(name, arm, part, removed)
                rows.append(r)
                print(json.dumps(r, ensure_ascii=False), flush=True)
            if len(universe) > 1:
                print(f"  (joint universe {'+'.join(universe)}: "
                      f"{removed_total} duplicates removed in all)", flush=True)

    os.makedirs(out, exist_ok=True)
    pd.DataFrame(rows).to_csv(os.path.join(out, "summary.csv"), index=False)

    print("\n=== check: test chunks shared with training, per arm ===", flush=True)
    check(raw, out, arms)
    print(f"\nwritten to {out}")


def check(raw, out, arms=ARMS):
    """The acceptance test: each arm must have no test chunk sharing what it groups by with training."""
    rows = []
    for arm in arms:
        for name, df in raw.items():
            assignment = pd.read_csv(os.path.join(out, arm, f"{name}.csv"), dtype={"chunk_id": str})
            d = df.merge(assignment[["chunk_id", "partition"]], on="chunk_id", how="inner")
            train, test = d[d.partition == "train"], d[d.partition == "test"]
            row = {"arm": arm, "dataset": name, "test": len(test)}
            for label, column in [("twin", "h_content_norm"), ("merge", "merge"), ("project", "project")]:
                row[label] = int(test[column].isin(set(train[column])).sum())
            rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(out, "contamination.csv"), index=False)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
