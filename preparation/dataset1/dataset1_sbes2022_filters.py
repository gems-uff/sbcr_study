#!/usr/bin/env python3
"""Where the 10,177 chunks of the SBES 2022 and JSERD 2024 studies come from, and how Dataset1 relates to them.

The code of the two studies, gems-uff/combination_conflicts_analysis at commit `db8f9aa`,
leaves its filters in three files of its `data/` folder, whose chunk ids are those of
`dataset.json` of the SBES 2022 dataset on FigShare:

- `malformed_chunks.csv`: the chunks with a conflict marker inside a version or a context;
- `resolution_composition.csv`: `v1_percentage` is -1 when the resolution could not be isolated;
- the chunks left are those of its `selected_chunks.py`, from which `filter_implicit_forks`
  removes the chunks of implicit forks. The inputs of that last step are not in the
  repository, so it is not reproduced here.

The script checks that the ids of `dataset.json` are those of the results of that code, counts
each filter, and counts the Dataset1 chunks (`dataset_processed_base.json`) each filter discards.

Inputs: a clone of combination_conflicts_analysis (`--sbes`), `dataset.json` (`--source`) and
`dataset_processed_base.json` (`--package`).
Outputs, in `--out`: `dataset1_sbes2022_filters.txt` and `dataset1_outside_sbes2022.csv`.

    python -I preparation/dataset1/dataset1_sbes2022_filters.py --sbes <clone> \
        --source <dataset.json> --package <dataset_processed_base.json> --out <dir>
"""
import argparse
import hashlib
import os

import pandas as pd


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sbes", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--package", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    sbes = os.path.expanduser(args.sbes)
    paths = {"malformed": os.path.join(sbes, "data", "malformed_chunks.csv"),
             "composition": os.path.join(sbes, "data", "resolution_composition.csv"),
             "partial_order": os.path.join(sbes, "data", "partial_order_result.csv"),
             "source": os.path.expanduser(args.source), "package": os.path.expanduser(args.package)}
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)

    malformed = set(pd.read_csv(paths["malformed"]).chunk_id)
    composition = pd.read_csv(paths["composition"])
    partial_order = pd.read_csv(paths["partial_order"])
    source = set(pd.read_json(paths["source"]).chunk_id)
    dataset1 = set(pd.read_json(paths["package"]).chunk_id)
    not_isolated = set(composition[composition.v1_percentage == -1].chunk_id)
    selected = set(composition.chunk_id) - malformed - not_isolated

    same_ids = source == set(composition.chunk_id) == set(partial_order.chunk_id)
    lines = [f"{k}: {v}\n  sha256 {sha256(v)}" for k, v in paths.items()]
    lines += ["",
              f"ids of dataset.json equal to those of resolution_composition.csv and partial_order_result.csv: {same_ids}",
              f"source chunks: {len(source):,}",
              f"with a conflict marker (malformed_chunks.csv): {len(malformed):,}",
              f"resolution not isolated (v1_percentage == -1): {len(not_isolated):,}, "
              f"{len(not_isolated - malformed):,} of them without a conflict marker",
              f"left before the implicit forks: {len(selected):,}",
              "",
              f"Dataset1 chunks: {len(dataset1):,}, all in the source: {dataset1 <= source}",
              f"  with a conflict marker: {len(dataset1 & malformed):,}",
              f"  resolution not isolated, without a conflict marker: {len(dataset1 & (not_isolated - malformed)):,}",
              f"  among the chunks left before the implicit forks: {len(dataset1 & selected):,}"]
    report = "\n".join(lines)
    print(report)
    open(os.path.join(out, "dataset1_sbes2022_filters.txt"), "w").write(report + "\n")
    outside = sorted(dataset1 - selected)
    pd.DataFrame({"chunk_id": outside,
                  "conflict_marker": [c in malformed for c in outside],
                  "resolution_not_isolated": [c in not_isolated for c in outside]}).to_csv(
        os.path.join(out, "dataset1_outside_sbes2022.csv"), index=False)

    if not same_ids or not dataset1 <= source:
        raise SystemExit("the ids do not match")


if __name__ == "__main__":
    main()
