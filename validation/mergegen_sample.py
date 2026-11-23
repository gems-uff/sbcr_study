#!/usr/bin/env python3
"""Smoke test of MergeGen's inference: regenerates the candidates of a few test conflicts and
compares them with the stored ones.

For each dataset of a root, the script loads the checkpoint of the models archive, generates
the candidate of the first `--n` test conflicts of the split, in the order of the dataset, with
the code of `mergegen/jit_inference.py`, and compares each candidate with the one stored in
`mergeGen/JIT/` of the results archive. The times are not compared: they depend on the machine.

Inputs: the data folder of a root (`--data`, with `{dataset}.json` and `split_{dataset}_{arm}.csv`),
the checkpoints (`--models`, with `{dataset}_{arm}/best_model.pt`), the stored candidates
(`--stored`, with `{dataset}_{arm}/model_{dataset}_{arm}/candidates.json`) and the backbone
(`--backbone`, `codet5-small-local`).
Output: one line per conflict and a summary, on the standard output; exit code 1 if a candidate
differs.

    python validation/mergegen_sample.py --data <archives>/partition-1/data \
        --models <archives>/partition-1/mergeGen/MODELS --stored <archives>/partition-1/mergeGen/JIT \
        --backbone <dir>/codet5-small-local --n 5
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE / "mergegen"))

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]


def first_test_conflicts(data_dir, name, arm, n):
    data = json.load(open(data_dir / f"{name}.json"))
    split = pd.read_csv(data_dir / f"split_{name}_{arm}.csv", dtype={"chunk_id": str})
    test = set(split[split.partition == "test"].chunk_id)
    ids = list(map(str, data["chunk_id"]))
    indices = [i for i, c in enumerate(ids) if c in test][:n]
    return [(ids[i], data["all_raw_base"][i], data["all_raw_a"][i], data["all_raw_b"][i]) for i in indices]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", required=True, type=Path, help="data folder of the root")
    p.add_argument("--models", required=True, type=Path, help="folder of the checkpoints (MODELS)")
    p.add_argument("--stored", required=True, type=Path, help="folder of the stored candidates (JIT)")
    p.add_argument("--backbone", required=True, type=Path, help="folder codet5-small-local")
    p.add_argument("--arm", default="mg")
    p.add_argument("--n", type=int, default=5, help="conflicts per dataset")
    p.add_argument("--datasets", nargs="*", default=DATASETS)
    args = p.parse_args()

    data_dir, models, stored = args.data.resolve(), args.models.resolve(), args.stored.resolve()
    backbone = args.backbone.resolve()

    # MergeInference reads ./codet5-small-local from the working directory
    work = Path(tempfile.mkdtemp(prefix="mergegen-sample-"))
    (work / "codet5-small-local").symlink_to(backbone)
    os.chdir(work)

    import torch
    from jit_inference import generate
    from mergegen_inference import MergeInference

    synchronize = torch.cuda.synchronize if torch.cuda.is_available() else (lambda: None)
    print(f"device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}")

    equal = total = 0
    for name in args.datasets:
        model = f"{name}_{args.arm}"
        expected = json.load(open(stored / model / f"model_{model}" / "candidates.json"))
        tool = MergeInference(model_path=str(models / model / "best_model.pt"))
        for chunk_id, base, a, b in first_test_conflicts(data_dir, name, args.arm, args.n):
            candidate, _ = generate(tool, base, a, b, synchronize)
            same = candidate == expected[chunk_id]
            equal += same
            total += 1
            print(f"{model}  {chunk_id}  {'equal' if same else 'DIFFERENT'}", flush=True)
        del tool
        torch.cuda.empty_cache()

    print(f"\n{equal}/{total} candidates equal to the stored ones")
    sys.exit(0 if equal == total else 1)


if __name__ == "__main__":
    main()
