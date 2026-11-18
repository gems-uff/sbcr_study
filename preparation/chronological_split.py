#!/usr/bin/env python3
"""Chronological split of the merge-grouped design.

Within each dataset, every training merge is older than every validation merge, and every
validation merge older than every test merge. The universe, the deduplication and the groups
are those of `make_splits.py` (arm `mg`), and the acceptance test is its `check`.

- The partition of a group is set by the committer date of its merge, with one cut per
  dataset, since the datasets cover different periods.
- The cuts are calibrated on the combination subset: the test takes the most recent merges
  until its combination conflicts come closest to the evaluated test of the merge-grouped
  design (`TARGET`), and the validation the next ones until the same size. A cut always falls
  between two distinct timestamps, so the order is strict.
- Merges without a date are left out of every partition.
- A group that alone would take more than `--cap` of the test partition of its dataset and
  whose date falls in the test period is left out too, since sending it to training would
  break the order. The cut is repeated until no large group is left in the test period.
- There is no seed: the assignment is deterministic.

Dataset1 and Dataset2_Java are cut separately, so the crossed evaluation of RQ3 between them
is not chronological.

Inputs: the datasets in `--data-root`, `commit_dates.csv` of `commit_dates.py` (`--dates`).
Outputs, in `--out`: `mg/<dataset>.csv` (chunk_id, partition, group), `excluded_groups.csv`,
`summary.csv` (the columns of `make_splits.summary`, plus the chunks left out, the cut dates
and the combination conflicts per partition), `acceptance_check.csv` and `chrono_split.json`
(the cut dates, the check of the strict order and the hash of the dates file).

    python preparation/chronological_split.py --data-root <data> --dates <dir>/commit_dates.csv --out <root>/splits
"""

import argparse
import hashlib
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_splits import check, deduplicate, groups, prepare, summary  # noqa: E402
from survey import LANGUAGES, load_dataset1, load_dataset2  # noqa: E402

ARM = "mg"
UNIVERSES = [["dataset1", "dataset2_Java"], ["dataset2_CSharp"], ["dataset2_JavaScript"], ["dataset2_TypeScript"]]
# Evaluated test of the merge-grouped design (combination subset of the test partition).
TARGET = {"dataset1": 549, "dataset2_Java": 1717, "dataset2_CSharp": 546,
          "dataset2_JavaScript": 1207, "dataset2_TypeScript": 392}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_dates(path):
    """`project@commit` -> committer date, the merge key of `survey.py`."""
    d = pd.read_csv(path, dtype=str)
    d = d[d.status == "found"]
    return dict(zip(d.repo + "@" + d.commit, pd.to_datetime(d.committed_date, utc=True)))


def take_latest(per_timestamp, target):
    """Number of most recent timestamps whose combination count comes closest to `target`.

    `per_timestamp` is the combination count per distinct timestamp, most recent first. On a
    tie, the smaller count is taken, so that the older partition keeps it.
    """
    cumulative = per_timestamp.cumsum().values
    best = min(range(len(cumulative) + 1),
               key=lambda k: (abs((cumulative[k - 1] if k else 0) - target), k))
    return best


def cut(part, target, limit):
    """Partition of each group of one dataset (NaN for a group left out), and the cut dates.

    `limit` is the largest number of chunks a group may have in the test period.
    """
    per_group = part.groupby("group").agg(date=("date", "max"), first=("date", "min"),
                                          chunks=("chunk_id", "size"), combination=("combination", "sum"))
    spanning = int((per_group.date != per_group["first"]).sum())
    large = per_group.chunks > limit
    excluded = pd.Series(False, index=per_group.index)
    while True:
        kept = per_group[~excluded]
        per_timestamp = kept.groupby("date").combination.sum().sort_index(ascending=False)
        k_test = take_latest(per_timestamp, target)
        test_from = per_timestamp.index[k_test - 1]
        newly = large & ~excluded & (per_group.date >= test_from)
        if not newly.any():
            break
        excluded |= newly

    rest = per_timestamp.iloc[k_test:]
    k_val = take_latest(rest, target)
    val_from = rest.index[k_val - 1]

    destination = pd.Series("train", index=per_group.index)
    destination[per_group.date >= val_from] = "validation"
    destination[per_group.date >= test_from] = "test"
    destination[excluded] = None
    return destination, per_group[excluded], {"validation_from": str(val_from), "test_from": str(test_from),
                                              "groups_spanning_dates": spanning,
                                              "large_group_limit": int(limit)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--dates", required=True, help="commit_dates.csv of the whole universe (commit_dates.py)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap", type=float, default=0.05,
                    help="largest share of the test partition (10%% of the dataset's chunks) a group may take")
    args = ap.parse_args()
    root = os.path.expanduser(args.data_root)
    out = os.path.expanduser(args.out)
    dates = load_dates(os.path.expanduser(args.dates))

    print("loading data...", flush=True)
    raw = {"dataset1": prepare("dataset1", load_dataset1(root))}
    for lang in LANGUAGES:
        raw[f"dataset2_{lang}"] = prepare(f"dataset2_{lang}", load_dataset2(root, lang))

    rows, cuts, order, excluded_all = [], {}, {}, []
    os.makedirs(os.path.join(out, ARM), exist_ok=True)
    for universe in UNIVERSES:
        together = pd.concat([raw[n] for n in universe], ignore_index=True)
        together, _ = deduplicate(together)
        together["group"] = groups(together, ARM)
        together["date"] = together["merge"].map(dates)
        together["combination"] = together.stratum.str.endswith("|combination").astype(int)

        for name in universe:
            part = together[together.dataset == name]
            dated = part[part.date.notna()].copy()
            limit = args.cap * 0.1 * len(dated)
            destination, excluded, cuts[name] = cut(dated, TARGET[name], limit)
            dated["partition"] = dated.group.map(destination)
            left_out = dated.partition.isna()
            first_merge = dated.drop_duplicates("group").set_index("group")["merge"]
            excluded_all.append(excluded.assign(dataset=name, merge=first_merge.reindex(excluded.index))
                                .reset_index()[["dataset", "group", "merge", "date", "chunks", "combination"]])
            dated = dated[~left_out]
            dated[["chunk_id", "partition", "group"]].to_csv(os.path.join(out, ARM, f"{name}.csv"), index=False)

            span = dated.groupby("partition").date.agg(["min", "max"])
            order[name] = bool(span.loc["train", "max"] < span.loc["validation", "min"]
                               and span.loc["validation", "max"] < span.loc["test", "min"])
            row = summary(name, ARM, dated, len(raw[name]) - len(part))
            comb = dated.groupby("partition").combination.sum()
            row.update({"undated_left_out": int(part.date.isna().sum()),
                        "large_groups_left_out": len(excluded), "large_group_chunks_left_out": int(left_out.sum()),
                        "combination_train": int(comb.get("train", 0)),
                        "combination_validation": int(comb.get("validation", 0)),
                        "combination_test": int(comb.get("test", 0)),
                        "combination_test_target": TARGET[name],
                        **{k: v for k, v in cuts[name].items()},
                        "train_first": str(span.loc["train", "min"]), "test_last": str(span.loc["test", "max"])})
            rows.append(row)
            print(json.dumps(row), flush=True)

    pd.DataFrame(rows).to_csv(os.path.join(out, "summary.csv"), index=False)
    pd.concat(excluded_all, ignore_index=True).to_csv(os.path.join(out, "excluded_groups.csv"), index=False)
    print("\n=== acceptance: contamination of the test by the training ===", flush=True)
    check(raw, out, [ARM])

    result = {"arm": ARM, "target": TARGET, "cap": args.cap, "cuts": cuts, "strict_order": order,
              "dates": {os.path.expanduser(args.dates): sha256(os.path.expanduser(args.dates))}}
    with open(os.path.join(out, "chrono_split.json"), "w") as f:
        json.dump(result, f, indent=2)
    if not all(order.values()):
        sys.exit(f"the order train < validation < test does not hold in {[n for n, ok in order.items() if not ok]}")
    print(f"\nstrict order train < validation < test: ok in the five datasets\nwritten to {out}")


if __name__ == "__main__":
    main()
