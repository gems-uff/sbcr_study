#!/usr/bin/env python3
"""SBCR's similarity per conflict, with the conflicts above SBCR's size limit scored 0.

A library. `sbcr_similarity.py` writes `sbcr_similarities.csv` only for the evaluations with
status `ok`. SBCR does not search a conflict with a version of 20,000 characters or more and
records it as `OUT_OF_LIMITS`. `load_sbcr_similarities` adds those conflicts with similarity
0, the score of an empty candidate, so that SBCR's size limit counts against it as MergeGen's
token limit counts against MergeGen. Every analysis that compares the two approaches loads
SBCR through it. It also checks that the CSV still matches the result spreadsheets of the
`sbcr/eval_*` folders. Other statuses (exceptions raised by SBCR) are reported and left out.

`sbcr_data_file` and `sbcr_chunk_ids` name the file SBCR reads for one partition and the
chunks it holds.
"""
import glob
import json
import os
import re

import pandas as pd

OK = "ok"
OUT_OF_LIMITS = "OUT_OF_LIMITS"
KEYS = ["target", "arm", "seed", "partition", "chunk_id"]

# The similarity the analyses read, with all whitespace removed. `sim_lcs_full` removes only
# spaces and line breaks, so tabs count; the RQ4 draw defined its bands with it.
SIM = "sim_lcs_no_whitespace"
SIM_DRAW = "sim_lcs_full"

# Dataset whose chunks each evaluation target holds. The RQ3 targets use the other
# dataset's configuration on these chunks.
BASE = {"dataset1": "dataset1", "rq3_ds1": "dataset1", "rq3_java": "dataset2_Java",
        "dataset2_Java": "dataset2_Java", "dataset2_CSharp": "dataset2_CSharp",
        "dataset2_JavaScript": "dataset2_JavaScript", "dataset2_TypeScript": "dataset2_TypeScript"}


def sbcr_data_file(root, dataset, arm, part="testing"):
    """The file SBCR reads for one partition of `root`, as `prepare_sbcr.py` writes it.

    For Dataset2 it is the combination subset of the partition. Dataset1 holds only
    combination conflicts and enters whole.
    """
    if dataset == "dataset1":
        return f"{root}/data/{dataset}_{arm}_{part}.json"
    return f"{root}/data/{dataset}_{arm}_combination_{part}.json"


def sbcr_chunk_ids(root, dataset, arm, part="testing"):
    """Chunk ids, as strings, of the file SBCR reads for one partition."""
    return set(map(str, json.load(open(sbcr_data_file(root, dataset, arm, part)))["chunk_id"]))


def parse_evaluation_folder(folder):
    """(target, arm, seed, partition) of an `sbcr/eval_*` folder, or None.

    `eval_common_<target>_<arm>` is the common test set: the test partition of `pd`,
    evaluated with the configuration of `<arm>` and seed 3022024.
    """
    label = os.path.basename(folder).replace("eval_", "")
    if label.startswith("common_"):
        m = re.match(r"common_(.+)_(control|mg)$", label)
        if not m:
            return None
        target, arm = m.groups()
        return target, arm, "3022024", "pd"
    m = re.match(r"(.+)_(control|mg|pd)_s(\d+)$", label)
    if not m:
        return None
    target, arm, seed = m.groups()
    return target, arm, seed, arm


def _results(root, seeds=None):
    """Status of every chunk in the SBCR result spreadsheets, one row per evaluation and chunk.

    With `seeds`, only the evaluation folders of those seeds are read.
    """
    parts = []
    for folder in sorted(glob.glob(f"{root}/sbcr/eval_*")):
        parsed = parse_evaluation_folder(folder)
        files = glob.glob(f"{folder}/RESULTS/*.xlsx")
        if parsed is None or not files:
            continue
        target, arm, seed, partition = parsed
        if seeds is not None and seed not in seeds:
            continue
        d = pd.read_excel(files[0], usecols=["chunk_id", "status"], dtype={"chunk_id": str})
        parts.append(d.assign(target=target, arm=arm, seed=seed, partition=partition,
                              status=d.status.astype(str), folder=folder))
    if not parts:
        return pd.DataFrame(columns=KEYS + ["status", "folder"])
    return pd.concat(parts, ignore_index=True)[KEYS + ["status", "folder"]]


def _check_csv(root, sb, ok):
    """`sbcr_similarities.csv` must hold every `ok` chunk that has a saved candidate, and nothing else.

    An `ok` chunk with no file in `OUTPUT/` is skipped by `sbcr_similarity.py`; it is
    reported here and stays out.
    """
    both = ok.merge(sb[KEYS], on=KEYS, how="outer", indicator=True)
    extra = both[both._merge == "right_only"]
    missing = both[both._merge == "left_only"]
    has_candidate = [os.path.exists(f"{r.folder}/OUTPUT/{r.chunk_id}") for r in missing.itertuples()]
    stale = int(sum(has_candidate))
    if stale or len(extra):
        raise RuntimeError(
            f"{root}/sbcr_similarities.csv does not match the SBCR result spreadsheets: {stale} `ok` "
            f"chunks with a candidate are missing and {len(extra)} rows have no `ok` status. "
            f"Run sbcr_similarity.py again.")
    if len(missing):
        print(f"warning: {len(missing)} SBCR evaluations have status `ok` but no saved candidate, "
              f"and are left out: {missing.groupby(['target', 'arm']).size().to_dict()}", flush=True)


def load_sbcr_similarities(root, out_of_limits="zero", seeds=None):
    """`sbcr_similarities.csv` plus a `status` column.

    With `out_of_limits="zero"`, each `OUT_OF_LIMITS` chunk is added with similarity 0 and
    exact match 0. With `"exclude"`, they are left out, the sensitivity check. With `seeds`
    (strings), only the rows and result spreadsheets of those seeds are read and checked.
    """
    if out_of_limits not in ("zero", "exclude"):
        raise ValueError(f"out_of_limits must be 'zero' or 'exclude', got {out_of_limits!r}")
    sb = pd.read_csv(f"{root}/sbcr_similarities.csv", dtype={"chunk_id": str, "seed": str})
    if SIM not in sb.columns:
        raise RuntimeError(f"{root}/sbcr_similarities.csv has no column {SIM}. Run sbcr_similarity.py again.")
    if seeds is not None:
        seeds = {str(s) for s in seeds}
        sb = sb[sb.seed.isin(seeds)].copy()
    sb["status"] = OK
    results = _results(root, seeds)
    _check_csv(root, sb, results[results.status == OK])
    failed = results[~results.status.isin([OK, OUT_OF_LIMITS])]
    if len(failed):
        print(f"warning: {len(failed)} SBCR evaluations ended in an exception and are left out: "
              f"{failed.groupby(['target', 'arm']).size().to_dict()}", flush=True)
    if out_of_limits == "exclude":
        return sb
    zero = results[results.status == OUT_OF_LIMITS].drop(columns="folder")
    zero[SIM_DRAW] = 0.0
    zero[SIM] = 0.0
    zero["exact_match_full"] = 0.0
    return pd.concat([sb, zero], ignore_index=True)


def sbcr_per_conflict(sb, keys):
    """Mean SBCR similarity and exact match over seeds per conflict, and whether it was out of limits.

    The size limit does not depend on the seed, so a conflict is out of limits in all seeds or in none.
    """
    flagged = sb.assign(out_of_limits=sb.status == OUT_OF_LIMITS)
    return (flagged.groupby(keys)
            .agg(sbcr=(SIM, "mean"), sbcr_em=("exact_match_full", "mean"),
                 out_of_limits=("out_of_limits", "any"))
            .reset_index())
