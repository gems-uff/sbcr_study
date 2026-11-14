#!/usr/bin/env python3
"""Exact duplicates, groups and overlap between the datasets.

Counts the exact duplicates of each dataset, how its chunks group by merge and by
project, how much of the test partition of the submitted version shares a merge, a
project or its content with the training partition, and the overlap between Dataset1
and Dataset2_Java. It is also the library that loads the two datasets for the other
preparation and analysis scripts.

Inputs: `dataset1_complete.json`, `dataset1_metadata.csv`, `dataset2_<language>_complete.json`,
`dataset2_<language>_metadata.json` and the combination partitions of the submitted version,
all in `--data-root`.
Outputs: `<out>.csv`, one row per dataset, and `<out>_overlap_dataset1_dataset2_java.json`.

    python preparation/survey.py --data-root <data> --out <dir>/survey
"""
import argparse
import json
import os
from hashlib import blake2b

import pandas as pd

SUBMITTED_SEED = 27082024
LANGUAGES = ["Java", "CSharp", "JavaScript", "TypeScript"]


def text_hash(*parts):
    h = blake2b(digest_size=16)
    for p in parts:
        h.update(("" if p is None else str(p)).encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()


def without_spaces(text):
    return "".join(str(text or "").split())


def normalize_project(value):
    """`https://github.com/owner/name` and `owner/name` name the same project."""
    s = str(value).strip().rstrip("/").lower()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.removesuffix(".git")


def submitted_split(chunk_ids):
    """The random 80/10/10 split of the submitted version over n rows."""
    n = len(chunk_ids)
    order = pd.DataFrame({"chunk_id": list(chunk_ids)}).sample(frac=1, random_state=SUBMITTED_SEED)
    end_train = int(n * 0.8)
    end_val = end_train + int(n * 0.1)
    return {
        "train": set(order.iloc[:end_train].chunk_id),
        "validation": set(order.iloc[end_train:end_val].chunk_id),
        "test": set(order.iloc[end_val:].chunk_id),
    }


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def fork_components(df):
    """Groups the projects linked by a shared commit (forks)."""
    uf = UnionFind()
    for project in df.project.unique():
        uf.find(project)
    for _, group in df.groupby("commit"):
        projects = group.project.unique()
        for p in projects[1:]:
            uf.union(projects[0], p)
    return df.project.map(uf.find)


def load_dataset1(root):
    raw = json.load(open(os.path.join(root, "dataset1_complete.json")))
    df = pd.DataFrame(raw)
    df["chunk_id"] = df.chunk_id.astype(str)
    meta = pd.read_csv(os.path.join(root, "dataset1_metadata.csv"))
    meta["chunk_id"] = meta.chunk_id.astype(str)
    meta = meta[["chunk_id", "project", "sha", "path"]].rename(columns={"sha": "commit", "path": "file"})
    meta["project"] = meta.project.map(normalize_project)
    # Dataset1 prefixes the path with the project, Dataset2 keeps it relative to the
    # repository. The prefix is removed so that the two compare.
    meta["file"] = [
        c[len(p) + 1:] if str(c).lower().startswith(p + "/") else c
        for c, p in zip(meta.file.astype(str), meta.project)
    ]
    meta["merge"] = meta.project + "@" + meta["commit"].astype(str)
    meta["merge_file"] = meta["merge"] + "/" + meta.file.astype(str)
    df = df.merge(meta, on="chunk_id", how="left")
    return df


def load_dataset2(root, language):
    raw = json.load(open(os.path.join(root, f"dataset2_{language}_complete.json")))
    df = pd.DataFrame(raw)
    df["chunk_id"] = df.merge_id.astype(str) + "-" + df.chunk_number.astype(str)
    meta = pd.DataFrame(json.load(open(os.path.join(root, f"dataset2_{language}_metadata.json"))))
    meta["chunk_id"] = meta.chunk_id.astype(str)
    meta = meta[["chunk_id", "mergeId", "repo", "commitHash", "fileName"]].rename(
        columns={"mergeId": "merge_file", "repo": "project", "commitHash": "commit", "fileName": "file"}
    )
    meta["project"] = meta.project.map(normalize_project)
    # `mergeId` identifies a file inside a merge, not the merge. The merge is the
    # (repo, commitHash) pair.
    meta["merge"] = meta.project + "@" + meta["commit"].astype(str)
    meta["merge_file"] = meta["merge"] + "/" + meta.file.astype(str).astype(str)
    meta["merge"] = meta["merge"].astype(str)
    df = df.merge(meta, on="chunk_id", how="left")
    return df


def combination_ids(root, name):
    """The evaluated chunks (the combination subset) of each partition of the submitted version."""
    if name == "dataset1":
        return None
    out = {}
    for partition, suffix in [("train", "training"), ("validation", "validation"), ("test", "testing")]:
        path = os.path.join(root, f"{name}_combination_{suffix}.json")
        out[partition] = set(map(str, json.load(open(path))["chunk_id"]))
    return out


def analyze(name, df, root):
    df = df.copy()
    df["h_content"] = [
        text_hash(b, a, bb, r)
        for b, a, bb, r in zip(df.all_raw_base, df.all_raw_a, df.all_raw_b, df.all_raw_res)
    ]
    df["h_content_norm"] = [
        text_hash(without_spaces(b), without_spaces(a), without_spaces(bb), without_spaces(r))
        for b, a, bb, r in zip(df.all_raw_base, df.all_raw_a, df.all_raw_b, df.all_raw_res)
    ]
    df["h_input"] = [
        text_hash(without_spaces(b), without_spaces(a), without_spaces(bb))
        for b, a, bb in zip(df.all_raw_base, df.all_raw_a, df.all_raw_b)
    ]
    df["fork_component"] = fork_components(df)

    partitions = submitted_split(df.chunk_id)
    df["partition"] = df.chunk_id.map({c: p for p, ids in partitions.items() for c in ids})

    combination = combination_ids(root, name)
    if combination is None:
        evaluated = df[df.partition == "test"]
    else:
        evaluated = df[df.chunk_id.isin(combination["test"])]
    train = df[df.partition == "train"]

    def shared(column):
        return int(evaluated[column].isin(set(train[column])).sum())

    r = {
        "dataset": name,
        "rows": len(df),
        "unique_chunk_ids": int(df.chunk_id.nunique()),
        "exact_duplicates": len(df) - int(df.h_content.nunique()),
        "exact_duplicates_normalized": len(df) - int(df.h_content_norm.nunique()),
        "duplicates_same_input": len(df) - int(df.h_input.nunique()),
        "merges": int(df["merge"].nunique()),
        "merge_files": int(df["merge_file"].nunique()),
        "projects": int(df.project.nunique()),
        "fork_components": int(df.fork_component.nunique()),
        "test_total": len(df[df.partition == "test"]),
        "evaluated_in_test": len(evaluated),
        "evaluated_with_exact_twin_in_train": shared("h_content_norm"),
        "evaluated_with_same_input_in_train": shared("h_input"),
        "evaluated_with_merge_in_train": shared("merge"),
        "evaluated_with_merge_file_in_train": shared("merge_file"),
        "evaluated_with_project_in_train": shared("project"),
        "evaluated_with_fork_component_in_train": shared("fork_component"),
    }
    for key in [
        "evaluated_with_exact_twin_in_train",
        "evaluated_with_same_input_in_train",
        "evaluated_with_merge_in_train",
        "evaluated_with_merge_file_in_train",
        "evaluated_with_project_in_train",
        "evaluated_with_fork_component_in_train",
    ]:
        r[key + "_pct"] = round(100 * r[key] / max(r["evaluated_in_test"], 1), 1)
    return r, df


def overlap_dataset1_dataset2_java(df1, df2):
    def values(df, column):
        return set(df[column].dropna())

    def files(df):
        return set(df.project.astype(str) + "/" + df.file.astype(str))

    projects1, projects2 = values(df1, "project"), values(df2, "project")
    return {
        "projects_dataset1": len(projects1),
        "projects_dataset2_Java": len(projects2),
        "shared_projects": len(projects1 & projects2),
        "shared_commits": len(values(df1, "commit") & values(df2, "commit")),
        "shared_files": len(files(df1) & files(df2)),
        "identical_conflicts": len(values(df1, "h_content_norm") & values(df2, "h_content_norm")),
        "identical_inputs": len(values(df1, "h_input") & values(df2, "h_input")),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-root", required=True, help="folder with the two datasets")
    p.add_argument("--out", required=True, help="prefix of the output files")
    args = p.parse_args()
    root = os.path.expanduser(args.data_root)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    rows, frames = [], {}
    print("loading dataset1...", flush=True)
    r, df = analyze("dataset1", load_dataset1(root), root)
    rows.append(r)
    frames["dataset1"] = df
    print(json.dumps(r, indent=2, ensure_ascii=False), flush=True)

    for language in LANGUAGES:
        name = f"dataset2_{language}"
        print(f"loading {name}...", flush=True)
        r, df = analyze(name, load_dataset2(root, language), root)
        rows.append(r)
        frames[name] = df
        print(json.dumps(r, indent=2, ensure_ascii=False), flush=True)

    pd.DataFrame(rows).to_csv(args.out + ".csv", index=False)

    overlap = overlap_dataset1_dataset2_java(frames["dataset1"], frames["dataset2_Java"])
    with open(args.out + "_overlap_dataset1_dataset2_java.json", "w") as f:
        json.dump(overlap, f, indent=2, ensure_ascii=False)

    print("\n=== overlap of Dataset1 and Dataset2_Java ===")
    print(json.dumps(overlap, indent=2, ensure_ascii=False))
    print(f"\nwritten to {args.out}.csv")


if __name__ == "__main__":
    main()
