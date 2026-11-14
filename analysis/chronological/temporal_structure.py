#!/usr/bin/env python3
"""Temporal structure of a partition of the merge-grouped design, and MergeGen's advantage over time.

The partitions assign groups of merges in random order, so the training of a test conflict holds
merges made after it. The script measures how much, and whether the difference between the
approaches changes with it, reading the results of one partition. Per dataset, over the
evaluated test conflicts of the `mg` arm:

1. coverage: share of training chunks and of evaluated test conflicts with a date;
2. future share: for each test conflict with date t, the share of the dated training chunks whose
   merge is later than t, and whether its project has a training chunk later than t;
3. the paired comparison SBCR against MergeGen (SBCR scores 0 above its size limit) per quartile
   of the test conflicts' date, the Spearman correlation between date and the per-conflict
   difference, and the comparison split by whether the conflict's project has a later training
   chunk. This reading is observational: the date of a conflict also changes its project mix and
   its size.

Also a library: `chunk_merges` gives the merge of each chunk to `chronological_effects.py`.

Inputs: the root (`--root`), `commit_dates.csv` (`--dates`) and the datasets (`--data-root`).
Outputs, in `--out`: `temporal_coverage.csv`, `future_share.csv`, `advantage_by_date.csv`,
`advantage_by_project_future.csv`, `test_conflict_dates.csv` and `temporal_structure.json`.

    python analysis/chronological/temporal_structure.py --root <root> --dates <dir>/commit_dates.csv \
        --data-root <data> --out <dir>
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rq1_rq3"))
sys.path.insert(0, str(HERE.parent / "similarity"))
sys.path.insert(0, str(HERE.parent.parent / "preparation"))
from compare_approaches import evaluated_sets, load_mergegen, paired_frames, split_key  # noqa: E402
from sbcr_scores import load_sbcr_similarities  # noqa: E402
from commit_dates import DATASETS, repo_from_url  # noqa: E402
ARM = "mg"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def chunk_merges(data_root):
    """chunk_id -> (repo in lower case, merge commit), per dataset, the key of `commit_dates.py`."""
    out = {}
    with open(data_root / "dataset1_metadata.csv", newline="") as f:
        out["dataset1"] = {row["chunk_id"]: (repo_from_url(row["url"]).lower(), row["sha"]) for row in csv.DictReader(f)}
    for name in DATASETS[1:]:
        meta = json.load(open(data_root / f"dataset2_{name.split('_', 1)[1]}_metadata.json"))
        out[name] = {str(c): (repo_from_url(r).lower(), h)
                     for c, r, h in zip(meta["chunk_id"], meta["repo"], meta["commitHash"])}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, required=True, help="experiment root")
    ap.add_argument("--dates", type=Path, required=True, help="commit_dates.csv of the whole universe")
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    root = args.root.expanduser()
    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)

    dates = pd.read_csv(args.dates.expanduser(), dtype=str)
    dates = dates[dates.status == "found"]
    date_of = {(r.repo, r.commit): pd.Timestamp(r.committed_date) for r in dates.itertuples()}
    merges = chunk_merges(args.data_root.expanduser())

    # Per-conflict pairs of the RQ1/RQ2 analysis, as compare_approaches.py builds them.
    evaluated = evaluated_sets(str(root))
    sb = load_sbcr_similarities(str(root))
    sb = sb[sb.partition == sb.arm]
    mg = load_mergegen(str(root), evaluated)
    pairs, _ = paired_frames(sb, mg)
    pairs = pairs[pairs.arm == ARM]

    coverage, future, advantage, by_project, per_conflict = [], [], [], [], []
    for name in DATASETS:
        split = pd.read_csv(root / "splits" / ARM / f"{name}.csv", dtype={"chunk_id": str})
        split["merge_key"] = split.chunk_id.map(merges[name])
        split["date"] = split.merge_key.map(lambda m: date_of.get(m) if isinstance(m, tuple) else None)
        split["project"] = split.merge_key.map(lambda m: m[0] if isinstance(m, tuple) else None)
        train = split[split.partition == "train"]
        test = split[split.chunk_id.isin(evaluated[split_key(name, ARM)])]
        coverage.append({"dataset": name, "train_chunks": len(train), "train_dated": train.date.notna().mean(),
                         "test_evaluated": len(test), "test_dated": test.date.notna().mean(),
                         "first_date": split.date.min().date(), "last_date": split.date.max().date()})

        train_dates = np.sort(train.date.dropna().values.astype("datetime64[ns]"))
        last_in_project = train.dropna(subset=["date"]).groupby("project").date.max()
        t = test.dropna(subset=["date"]).copy()
        tv = t.date.values.astype("datetime64[ns]")
        t["future_share"] = 1 - np.searchsorted(train_dates, tv, side="right") / len(train_dates)
        t["project_future"] = [p in last_in_project.index and last_in_project[p] > d for p, d in zip(t.project, t.date)]
        future.append({"dataset": name, "n": len(t),
                       "future_share_median": t.future_share.median(),
                       "future_share_q1": t.future_share.quantile(0.25),
                       "future_share_q3": t.future_share.quantile(0.75),
                       "test_with_half_training_later": (t.future_share >= 0.5).mean(),
                       "test_with_later_training_in_project": t.project_future.mean()})

        p = pairs[pairs.dataset == name].merge(t[["chunk_id", "date", "future_share", "project_future"]], on="chunk_id")
        p["difference"] = p.sbcr - p.mergegen
        p["date_quartile"] = pd.qcut(p.date.rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
        for q, g in p.groupby("date_quartile"):
            advantage.append({"dataset": name, "date_quartile": q, "n": len(g),
                              "from": g.date.min().date(), "to": g.date.max().date(),
                              "future_share_median": g.future_share.median(),
                              "sbcr": g.sbcr.mean(), "mergegen": g.mergegen.mean(), "difference": g.difference.mean(),
                              "mergegen_wins": (g.sbcr < g.mergegen).mean()})
        for flag, g in p.groupby("project_future"):
            by_project.append({"dataset": name, "later_training_in_project": bool(flag), "n": len(g),
                               "sbcr": g.sbcr.mean(), "mergegen": g.mergegen.mean(), "difference": g.difference.mean(),
                               "mergegen_wins": (g.sbcr < g.mergegen).mean()})
        rho, pval = spearmanr(p.date.map(pd.Timestamp.timestamp), p.difference)
        advantage.append({"dataset": name, "date_quartile": "all", "n": len(p), "from": p.date.min().date(),
                          "to": p.date.max().date(), "future_share_median": p.future_share.median(),
                          "sbcr": p.sbcr.mean(), "mergegen": p.mergegen.mean(), "difference": p.difference.mean(),
                          "mergegen_wins": (p.sbcr < p.mergegen).mean(), "spearman_date_difference": rho,
                          "spearman_p": pval})
        per_conflict.append(p.assign(dataset=name)[["dataset", "chunk_id", "date", "future_share", "project_future",
                                                    "out_of_limits", "sbcr", "mergegen", "difference", "date_quartile"]])

    tables = {"temporal_coverage.csv": pd.DataFrame(coverage), "future_share.csv": pd.DataFrame(future),
              "advantage_by_date.csv": pd.DataFrame(advantage),
              "advantage_by_project_future.csv": pd.DataFrame(by_project),
              "test_conflict_dates.csv": pd.concat(per_conflict, ignore_index=True)}
    for fname, t in tables.items():
        t.to_csv(out / fname, index=False)
    pd.set_option("display.width", 200)
    for fname in ["temporal_coverage.csv", "future_share.csv", "advantage_by_date.csv",
                  "advantage_by_project_future.csv"]:
        print(f"\n=== {fname} ===")
        print(tables[fname].round(4).to_string(index=False))

    summary = {"root": str(root), "arm": ARM,
               "inputs": {str(args.dates.expanduser()): sha256(args.dates.expanduser())},
               "outputs": {f: sha256(out / f) for f in tables}}
    (out / "temporal_structure.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
