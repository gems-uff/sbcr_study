#!/usr/bin/env python3
"""Counts over the candidates of both approaches: empty candidates, exact match and lines of V1 or V2 only.

Over the test partition of each arm. MergeGen's population is the whole test partition; SBCR's
is its combination subset (`preparation/combination.py`), and Dataset1 enters whole. The script
checks that the subset it rebuilds holds the chunks of the file SBCR read. Per dataset, arm and
approach:

- **empty**: empty text after `strip()`. For SBCR it also covers the chunks with no `ok` status,
  which have no output file, that is, those above its size limit; `status` keeps the status;
- **exact match**: equality with the developer's whole resolution with all whitespace removed,
  the same event as a similarity of 1. An empty candidate against an empty resolution counts;
- **made only of lines of V1 or V2**: the multiset of the candidate's normalized lines is
  contained in that of V1 plus V2. An empty candidate is left out (`None`) and counted as empty.

Input: the root (`--root`). Outputs: `population_candidates.csv` and `population_sizes.csv` in
the root, or `--out` and `<out>_sizes.csv`.

    python analysis/datasets/population_candidates.py --root <root> [--arms mg] [--seeds 3022024] [--out <csv>]
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "preparation"))
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from combination import normalized_lines, strategy  # noqa: E402
from sbcr_scores import OK, sbcr_chunk_ids, sbcr_data_file  # noqa: E402
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
ARMS = ["mg", "pd"]
SEEDS = ["31337", "7412", "98765", "3022024", "20260904"]  # the main one is 3022024


def normalize(t):
    return "".join(str(t).split())


def made_only_of_v1v2(candidate, v1, v2):
    candidate_lines = normalized_lines(candidate)
    if len(candidate_lines) == 0:
        return None  # empty candidate: counted apart
    left = Counter(candidate_lines) - (Counter(normalized_lines(v1)) + Counter(normalized_lines(v2)))
    return sum(left.values()) == 0


def load_data(root, name):
    d = json.load(open(f"{root}/data/{name}.json"))
    idx = {str(c): i for i, c in enumerate(d["chunk_id"])}
    return d, idx


def sbcr_population(name, data, idx, test_ids):
    """Subset of `test_ids` that SBCR evaluates.

    `prepare_sbcr.py` filters only the Dataset2 datasets, and Dataset1 enters whole, although
    the filter would drop one of its test chunks. The population here is what SBCR saw.
    """
    if name == "dataset1":
        return set(test_ids)
    out = set()
    for c in test_ids:
        i = idx[c]
        if strategy(data["all_raw_a"][i], data["all_raw_b"][i], data["all_raw_res"][i]) == "Combination":
            out.add(c)
    return out


def check_sbcr_population(root, name, arm, sbcr_ids):
    """The rebuilt subset must hold the chunks of the file SBCR read, when it exists."""
    file = sbcr_data_file(root, name, arm)
    if not os.path.exists(file):
        return
    read = sbcr_chunk_ids(root, name, arm)
    if read != sbcr_ids:
        raise SystemExit(f"{name}/{arm}: the rebuilt SBCR population differs from {file} "
                         f"({len(sbcr_ids - read)} only here, {len(read - sbcr_ids)} only there)")


def rows_mergegen(root, name, arm, data, idx, test_ids):
    cand_paths = glob.glob(f"{root}/mergeGen/JIT/{name}_{arm}/model_{name}_{arm}/candidates.json")
    if not cand_paths:
        print(f"  warning: no candidates.json for {name}/{arm}", flush=True)
        return []
    candidates = json.load(open(cand_paths[0]))
    rows = []
    for c in test_ids:
        i = idx[c]
        cand = candidates.get(c)
        if cand is None:
            continue
        v1, v2, res = data["all_raw_a"][i], data["all_raw_b"][i], data["all_raw_res"][i]
        rows.append({
            "dataset": name, "arm": arm, "approach": "mergegen", "seed": "", "status": "",
            "chunk_id": c, "empty": str(cand).strip() == "",
            "exact_match": normalize(cand) == normalize(res),
            "only_v1v2_lines": made_only_of_v1v2(cand, v1, v2),
        })
    return rows


def rows_sbcr(root, name, arm, data, idx, sbcr_ids, seeds):
    rows = []
    for seed in seeds:
        folder = f"{root}/sbcr/eval_{name}_{arm}_s{seed}"
        files = glob.glob(f"{folder}/RESULTS/*.xlsx")
        if not files:
            print(f"  warning: no RESULTS for {name}/{arm}/s{seed}", flush=True)
            continue
        d = pd.read_excel(files[0], dtype={"chunk_id": str})
        status_of = dict(zip(d.chunk_id, d.status.astype(str)))
        for c in sorted(sbcr_ids):
            i = idx[c]
            v1, v2, res = data["all_raw_a"][i], data["all_raw_b"][i], data["all_raw_res"][i]
            status = status_of.get(c, "")
            path = f"{folder}/OUTPUT/{c}"
            base = {"dataset": name, "arm": arm, "approach": "sbcr", "seed": seed,
                    "status": status, "chunk_id": c}
            if status != OK or not os.path.exists(path):
                rows.append({**base, "empty": True, "exact_match": False, "only_v1v2_lines": None})
                continue
            cand = open(path, encoding="utf-8", errors="replace").read()
            rows.append({**base, "empty": cand.strip() == "",
                         "exact_match": normalize(cand) == normalize(res),
                         "only_v1v2_lines": made_only_of_v1v2(cand, v1, v2)})
    return rows


def parse_list(text, allowed, what):
    items = [a.strip() for a in text.split(",") if a.strip()]
    unknown = [a for a in items if a not in allowed]
    if unknown or not items:
        raise SystemExit(f"unknown {what} {unknown}; choose among {allowed}")
    return items


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="experiment root")
    p.add_argument("--arms", default=",".join(ARMS), help="arms to count, comma-separated (default: mg,pd)")
    p.add_argument("--seeds", default=",".join(SEEDS), help="SBCR seeds, comma-separated (default: the five)")
    p.add_argument("--out", help="output CSV (default: population_candidates.csv in the root); "
                                 "the population sizes go beside it, with the suffix _sizes")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    arms = parse_list(args.arms, ARMS, "arms")
    seeds = parse_list(args.seeds, SEEDS, "seeds")
    out = (os.path.abspath(os.path.expanduser(args.out)) if args.out
           else os.path.join(root, "population_candidates.csv"))
    out_sizes = (os.path.splitext(out)[0] + "_sizes.csv" if args.out
                 else os.path.join(root, "population_sizes.csv"))

    rows, sizes = [], []
    for name in DATASETS:
        data, idx = load_data(root, name)
        for arm in arms:
            assignment = pd.read_csv(f"{root}/splits/{arm}/{name}.csv", dtype={"chunk_id": str})
            test_ids = list(assignment[assignment.partition == "test"].chunk_id)
            sbcr_ids = sbcr_population(name, data, idx, test_ids)
            check_sbcr_population(root, name, arm, sbcr_ids)

            sizes.append({"dataset": name, "arm": arm,
                          "n_mergegen": len(test_ids), "n_sbcr": len(sbcr_ids)})
            rows += rows_mergegen(root, name, arm, data, idx, test_ids)
            rows += rows_sbcr(root, name, arm, data, idx, sbcr_ids, seeds)
            print(f"{name}/{arm}: mergegen n={len(test_ids)}, sbcr n={len(sbcr_ids)}", flush=True)

    pd.DataFrame(rows).to_csv(out, index=False)
    pd.DataFrame(sizes).to_csv(out_sizes, index=False)
    print(f"\nwritten: {len(rows):,} rows in {out}, sizes in {out_sizes}")


if __name__ == "__main__":
    main()
