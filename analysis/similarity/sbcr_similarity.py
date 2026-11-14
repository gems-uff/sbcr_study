#!/usr/bin/env python3
"""Computes SBCR's similarity with the same function used for MergeGen.

SBCR's own `compare()` removes empty lines but keeps spaces, and reads the candidate back
from disk as `iso-8859-1`, which splits multibyte characters. Here the similarity is
recomputed from the saved candidate and the developer's whole resolution, in UTF-8, with
`2*|LCS| / (len1 + len2)`, as for MergeGen's candidates (`mergegen_similarity.py`). Two columns:

- `sim_lcs_no_whitespace`, over the text with all whitespace removed, which the analyses read;
- `sim_lcs_full`, over the text without spaces and line breaks only, so that tabs count,
  the column the RQ4 draw defined its bands with.

Only status `ok` is written. `sbcr_scores.py` adds the conflicts above SBCR's size limit when
the analyses load this file.

Inputs, under `--root`: `data/{dataset}.json` and the `sbcr/eval_*` folders.
Output: `<root>/sbcr_similarities.csv`, one row per evaluation and conflict.

    python analysis/similarity/sbcr_similarity.py --root <root>
"""
import argparse
import glob
import json
import os
import sys

import pandas as pd
import pylcs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sbcr_scores import BASE, OK, parse_evaluation_folder  # noqa: E402


def lcs(a, b):
    idx = pylcs.lcs_sequence_idx(a, b)
    return ''.join([b[i] for i in idx if i != -1])


def gestalt(a, b):
    if a == b:
        return 1.0
    if len(a) + len(b) == 0:
        return 0.0
    return 2 * len(lcs(a, b)) / (len(a) + len(b))


def without_spaces(t):
    return str(t).replace(' ', '').replace('\n', '')


def normalize(t):
    return ''.join(str(t).split())


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    root = os.path.expanduser(p.parse_args().root)

    resolutions = {}
    for name in set(BASE.values()):
        d = json.load(open(f"{root}/data/{name}.json"))
        resolutions[name] = {str(c): r for c, r in zip(d["chunk_id"], d["all_raw_res"])}

    rows = []
    for folder in sorted(glob.glob(f"{root}/sbcr/eval_*")):
        parsed = parse_evaluation_folder(folder)
        if parsed is None:
            continue
        target, arm, seed, partition = parsed
        res = resolutions[BASE[target]]
        files = glob.glob(f"{folder}/RESULTS/*.xlsx")
        if not files:
            continue
        d = pd.read_excel(files[0], dtype={"chunk_id": str})
        d = d[d.status == OK]
        for r in d.itertuples():
            path = f"{folder}/OUTPUT/{r.chunk_id}"
            if not os.path.exists(path):
                continue
            cand = open(path, encoding="utf-8", errors="replace").read()
            sol = res[str(r.chunk_id)]
            rows.append({"target": target, "arm": arm, "seed": seed,
                         "partition": partition,
                         "chunk_id": str(r.chunk_id),
                         "sim_lcs_full": gestalt(without_spaces(cand), without_spaces(sol)),
                         "sim_lcs_no_whitespace": gestalt(normalize(cand), normalize(sol)),
                         "exact_match_full": float(normalize(cand) == normalize(sol)),
                         "sim_original": r.solution_sim_lcs,
                         "time": r.time_seconds})
        print(f"{os.path.basename(folder).replace('eval_', '')}: {len(d)} conflicts", flush=True)

    t = pd.DataFrame(rows)
    t.to_csv(f"{root}/sbcr_similarities.csv", index=False)
    print(f"\nwritten: {len(t):,} rows")
    print(f"mean difference to the original column: {(t.sim_lcs_full - t.sim_original).mean():+.4f}")


if __name__ == "__main__":
    main()
