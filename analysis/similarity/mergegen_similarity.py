#!/usr/bin/env python3
"""Similarity of MergeGen's candidates to the developer's resolution.

The function is that of `sbcr_similarity.py`, `2*|LCS| / (len1 + len2)` against the whole
resolution, so that both approaches are scored by the same code. Columns of `similarities.csv`,
one row per candidate:

- `sim_lcs_no_whitespace`: with all whitespace removed, the column the analyses read;
- `sim_lcs_full`: with spaces and line breaks removed, so that tabs count, the column the RQ4
  draw defined its bands with;
- `sim_lcs_truncated`, `sim_difflib_truncated`, `sim_difflib_full`: the same against the
  reference MergeGen scores against, cut at 200 tokens (`preparation/truncated_references.py`),
  and with `difflib.SequenceMatcher`, for comparison;
- `exact_match_full`: equality with the whole resolution, with all whitespace removed;
- `reference_truncated`: whether the cut reference differs from the whole resolution.

A folder that already has `similarities.csv` is skipped. Runs in the `sbcr-analise` environment.

Inputs, under `--root`: `data/{dataset}.json`, `references/{dataset}.json` and
`mergeGen/JIT/*/model_*/candidates.json`.
Output: `similarities.csv` beside each `candidates.json`.

    python analysis/similarity/mergegen_similarity.py --root <root>
"""
import argparse
import difflib
import glob
import json
import os
import re
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sbcr_scores import SIM  # noqa: E402
from sbcr_similarity import gestalt, normalize, without_spaces  # noqa: E402

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]


def gestalt_difflib(a, b):
    """Ratio of difflib's SequenceMatcher."""
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def similarities(chunk, candidate, full, truncated):
    """One row of `similarities.csv`."""
    return {
        "chunk_id": chunk,
        "sim_lcs_full": gestalt(without_spaces(candidate), without_spaces(full)),
        SIM: gestalt(normalize(candidate), normalize(full)),
        "sim_lcs_truncated": gestalt(without_spaces(candidate), without_spaces(truncated)),
        "sim_difflib_truncated": gestalt_difflib(candidate, truncated),
        "sim_difflib_full": gestalt_difflib(candidate, full),
        "exact_match_full": float(normalize(candidate) == normalize(full)),
        "reference_truncated": full != truncated and normalize(full) != normalize(truncated),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    root = os.path.expanduser(p.parse_args().root)

    full, truncated = {}, {}
    for name in DATASETS:
        d = json.load(open(f"{root}/data/{name}.json"))
        full[name] = {str(c): r for c, r in zip(d["chunk_id"], d["all_raw_res"])}
        truncated[name] = json.load(open(f"{root}/references/{name}.json"))

    for cand_path in sorted(glob.glob(f"{root}/mergeGen/JIT/*/model_*/candidates.json")):
        target = os.path.dirname(cand_path)
        if os.path.exists(f"{target}/similarities.csv"):
            print(f"{target}: already done, skipped", flush=True)
            continue
        dataset_arm = os.path.basename(os.path.dirname(target))
        # the suffix __test_<arm> marks a model of one arm run on another arm's test set
        name = re.sub(r"__test_[a-z0-9]+$", "", dataset_arm).rsplit("_", 1)[0]
        candidates = json.load(open(cand_path))

        start = time.time()
        rows = []
        for k, (chunk, candidate) in enumerate(candidates.items()):
            rows.append(similarities(chunk, candidate, full[name][chunk], truncated[name][chunk]))
            if (k + 1) % 2000 == 0:
                print(f"  {dataset_arm}: {k+1}/{len(candidates)}", flush=True)
        pd.DataFrame(rows).to_csv(f"{target}/similarities.csv", index=False)
        print(f"{dataset_arm} <- {os.path.basename(target)[6:]}: {len(rows)} conflicts, "
              f"{(time.time()-start)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
