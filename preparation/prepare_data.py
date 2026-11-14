#!/usr/bin/env python3
"""Sets up the data tree of an experiment root: deduplicated data, splits and links.

Under `--root`:

    data/{dataset}.json               deduplicated content, one file per dataset
    data/split_{dataset}_{arm}.csv    chunk_id -> partition
    data/{dataset}_{arm}.json         link to the content, one name per arm
    mergeGen/                         MergeGen code, backbones and output folders
    mergeGen/PROCESSED/{dataset}/     tokenization, computed once per dataset
    mergeGen/PROCESSED/{dataset}_{arm}/  links to the tokenization, plus the partition slices

The tokenized blocks of a thousand chunks do not depend on the split, so the arms share
them through links, and only `processed_{train,valid,test}.pkl` differ per arm.

Inputs: the datasets in `--data-root`, `<root>/splits/<arm>/<dataset>.csv` (`make_splits.py`),
the MergeGen code (`--code`) and the CodeT5 backbones (`--backbones`).

    python preparation/prepare_data.py --data-root <data> --root <root> --backbones <dir> --arms mg
    python preparation/prepare_data.py --root <root> --links --arms mg   # after the tokenization
"""
import argparse
import json
import os
import shutil
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from survey import LANGUAGES, load_dataset1, load_dataset2  # noqa: E402

ARMS = ("control", "mg", "pd")
CODE = ("run_mergegen.py", "dataset.py", "dataset_parallel.py", "run_total_dataset.py",
        "mergegen_inference.py")
OUTPUTS = ("PROCESSED", "AUX_FILES", "MODELS", "OUTPUT", "RESULTS", "LOGS")


def link(target, name):
    if os.path.islink(name) or os.path.exists(name):
        os.remove(name) if os.path.islink(name) else None
    if not os.path.exists(name):
        os.symlink(target, name)


def write_data(df, chunk_ids, path):
    """Writes the chunks that survived, in the format MergeGen reads."""
    d = df[df.chunk_id.isin(chunk_ids)].reset_index(drop=True)
    out = {
        "chunk_id": d.chunk_id.tolist(),
        "all_raw_base": d.all_raw_base.tolist(),
        "all_raw_a": d.all_raw_a.tolist(),
        "all_raw_b": d.all_raw_b.tolist(),
        "all_raw_res": d.all_raw_res.tolist(),
    }
    if "merge_id" in d.columns:
        out["merge_id"] = d.merge_id.tolist()
        out["chunk_number"] = d.chunk_number.tolist()
    with open(path, "w") as f:
        json.dump(out, f)
    return len(d)


def link_tokenization(root, arms=ARMS):
    """Points the PROCESSED folder of each arm to the tokenization already computed."""
    processed = os.path.join(root, "mergeGen", "PROCESSED")
    names = ["dataset1"] + [f"dataset2_{language}" for language in LANGUAGES]
    for name in names:
        blocks = sorted(b for b in os.listdir(os.path.join(processed, name))
                        if b.startswith("processed_") and "_" in b[10:])
        blocks = [b for b in blocks if b not in ("processed_train.pkl", "processed_valid.pkl", "processed_test.pkl")]
        for arm in arms:
            destination = os.path.join(processed, f"{name}_{arm}")
            os.makedirs(destination, exist_ok=True)
            for block in blocks:
                link(os.path.join(processed, name, block), os.path.join(destination, block))
        print(f"{name}: {len(blocks)} blocks linked in {len(arms)} arms", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-root", help="folder with the two datasets (not needed with --links)")
    p.add_argument("--root", required=True, help="experiment root")
    p.add_argument("--code", default=os.path.join(HERE, "..", "mergegen"), help="folder with the MergeGen code")
    p.add_argument("--backbones", help="folder with codet5-small-local (not needed with --links)")
    p.add_argument("--links", action="store_true",
                   help="only link the shared tokenization, once it exists")
    p.add_argument("--arms", default=",".join(ARMS), help="arms present in splits/, comma-separated")
    args = p.parse_args()
    arms = [a for a in args.arms.split(",") if a]

    root = os.path.expanduser(args.root)
    if args.links:
        link_tokenization(root, arms)
        return
    if not args.data_root or not args.backbones:
        p.error("--data-root and --backbones are required without --links")
    source = os.path.expanduser(args.data_root)
    splits = os.path.join(root, "splits")
    data = os.path.join(root, "data")
    mergegen = os.path.join(root, "mergeGen")
    os.makedirs(data, exist_ok=True)
    for d in OUTPUTS:
        os.makedirs(os.path.join(mergegen, d), exist_ok=True)

    for file in CODE:
        shutil.copy2(os.path.join(os.path.expanduser(args.code), file), mergegen)
    for backbone in ("codet5-small-local", "codet5-base"):
        target = os.path.join(os.path.expanduser(args.backbones), backbone)
        if os.path.isdir(target):
            link(target, os.path.join(mergegen, backbone))
        else:
            print(f"  MISSING: {target}")

    names = ["dataset1"] + [f"dataset2_{language}" for language in LANGUAGES]
    for name in names:
        print(f"{name}...", flush=True)
        df = load_dataset1(source) if name == "dataset1" else load_dataset2(source, name.split("_", 1)[1])

        assignments = {a: pd.read_csv(os.path.join(splits, a, f"{name}.csv"), dtype={"chunk_id": str})
                       for a in arms}
        sets = {a: set(s.chunk_id) for a, s in assignments.items()}
        if len({frozenset(c) for c in sets.values()}) != 1:
            raise ValueError(f"{name}: the arms do not cover the same chunks")

        n = write_data(df, sets[arms[0]], os.path.join(data, f"{name}.json"))
        print(f"  {n} chunks in data/{name}.json", flush=True)

        for arm, assignment in assignments.items():
            label = f"{name}_{arm}"
            assignment[["chunk_id", "partition"]].to_csv(os.path.join(data, f"split_{label}.csv"), index=False)
            link(f"{name}.json", os.path.join(data, f"{label}.json"))
            os.makedirs(os.path.join(mergegen, "PROCESSED", label), exist_ok=True)

    print("\ndone. Next step, inside", mergegen)
    for name in names:
        print(f"  python run_total_dataset.py {name} dataset_parallel.py")


if __name__ == "__main__":
    main()
