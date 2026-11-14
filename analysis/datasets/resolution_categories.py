#!/usr/bin/env python3
"""Resolution categories of the Dataset2 conflicts, the combination subset, and the projects per language.

Classifies each chunk of the complete Dataset2 into the seven categories of
`preparation/combination.py` (V1, V2, ConcatV1V2, ConcatV2V1, New code, None, Combination), per
language and in all, checks that the Combination count of each language equals the size of
its combination partitions, and counts per language the projects of the complete dataset and
those that contribute combination chunks. It also classifies Dataset1.

Inputs, in `--data-root`: `dataset2_<language>_complete.json`, `dataset2_<language>_metadata.json`,
`dataset2_<language>_combination_{training,validation,testing}.json`, `dataset1_complete.json`
and `dataset1_{training,validation,testing}.json`.
Output: the tables, on the standard output.

    python analysis/datasets/resolution_categories.py --data-root <data>
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "preparation"))
from combination import strategy  # noqa: E402

LANGS = ["Java", "CSharp", "JavaScript", "TypeScript"]
CATS = ["V1", "V2", "ConcatV1V2", "ConcatV2V1", "New code", "None", "Combination"]
PARTS = ("training", "validation", "testing")


def load(root, name):
    return json.load(open(os.path.join(root, name), encoding="utf-8"))


def classify_complete(path):
    d = json.load(open(path, encoding="utf-8"))
    a, b, r = d["all_raw_a"], d["all_raw_b"], d["all_raw_res"]
    counter = collections.Counter(strategy(a[i], b[i], r[i]) for i in range(len(a)))
    return counter, len(a)


def line(counter):
    return "  ".join(f"{k}={counter.get(k, 0)}" for k in CATS)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-root", required=True)
    root = os.path.expanduser(p.parse_args().data_root)

    print("=" * 72)
    print("Resolution category of each chunk of the complete Dataset2")
    print("=" * 72)
    grand = collections.Counter()
    for lang in LANGS:
        counter, total = classify_complete(os.path.join(root, f"dataset2_{lang}_complete.json"))
        grand.update(counter)
        print(f"\n{lang}: total = {total}")
        print("  " + line(counter))
        assert sum(counter.values()) == total
    print("\nDataset2 (sum of the four languages):")
    print("  " + line(grand))
    print(f"  total = {sum(grand.values())}")
    excluded = sum(v for k, v in grand.items() if k != "Combination")
    print(f"  Combination (kept) = {grand['Combination']}   excluded = {excluded}")

    print("\n" + "=" * 72)
    print("Combination against the combination partitions")
    print("=" * 72)
    for lang in LANGS:
        counter, _ = classify_complete(os.path.join(root, f"dataset2_{lang}_complete.json"))
        comb = counter["Combination"]
        parts = {p: len(load(root, f"dataset2_{lang}_combination_{p}.json")["chunk_id"]) for p in PARTS}
        print(f"\n{lang}: Combination = {comb}   "
              f"train {parts['training']} / val {parts['validation']} / test {parts['testing']}"
              f"   (sum {sum(parts.values())})")
        assert comb == sum(parts.values())

    print("\n" + "=" * 72)
    print("Projects (unique repositories) per language")
    print("=" * 72)
    for lang in LANGS:
        meta_full = load(root, f"dataset2_{lang}_metadata.json")
        chunk_to_repo = dict(zip(meta_full["chunk_id"], meta_full["repo"]))
        comb_ids = set()
        for p in PARTS:
            comb_ids.update(load(root, f"dataset2_{lang}_combination_{p}.json")["chunk_id"])
        repos_all = set(meta_full["repo"])
        repos_comb = {chunk_to_repo[c] for c in comb_ids if c in chunk_to_repo}
        print(f"  {lang}: repositories in the complete dataset = {len(repos_all)}   "
              f"repositories with combination chunks = {len(repos_comb)}")

    print("\n" + "=" * 72)
    print("Dataset1 (filtered to combination by its source)")
    print("=" * 72)
    counter, total = classify_complete(os.path.join(root, "dataset1_complete.json"))
    print(f"total = {total}")
    print("  " + line(counter))
    parts = {p: len(load(root, f"dataset1_{p}.json")) for p in PARTS}
    print(f"partitions: train {parts['training']} / val {parts['validation']} / "
          f"test {parts['testing']}   (sum {sum(parts.values())})")


if __name__ == "__main__":
    main()
