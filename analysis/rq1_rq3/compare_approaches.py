#!/usr/bin/env python3
"""Pairs the two approaches by conflict and writes the tables of RQ1 to RQ3, for each arm of a root.

MergeGen's similarity (just-in-time candidates) and SBCR's (recomputed with the same function)
are joined by conflict, both with all whitespace removed and against the whole resolution
(`sim_lcs_no_whitespace`). SBCR enters as the mean of its seeds per conflict, and the spread
across seeds is written apart. The conflicts above SBCR's 20,000-character limit score 0 for
SBCR (`sbcr_scores.py`). `comparison.csv` also carries each comparison without those
conflicts, labeled `<analysis>_excluding_out_of_limits`, as a sensitivity check.

Also a library: `evaluated_sets`, `load_mergegen`, `paired_frames`, `paired_comparison` and
`paired_rank_biserial` are imported by the other analyses.

Inputs, under `--root`: `data/*_testing.json`, `sbcr_similarities.csv`, the `sbcr/eval_*`
folders and `mergeGen/JIT/*/model_*/similarities.csv`.
Outputs, in the root or `--out`: `comparison.csv` (one row per analysis, dataset and arm: means,
difference, wins, ties, paired rank-biserial, Wilcoxon p, medians and exact matches) and
`seed_spread.csv` (SBCR's mean similarity across seeds).

    python analysis/rq1_rq3/compare_approaches.py --root <root> [--out <dir>] [--seeds 3022024]
"""
import argparse
import glob
import json
import os
import sys

import pandas as pd
from scipy.stats import wilcoxon

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "similarity"))
from sbcr_scores import SIM, load_sbcr_similarities, sbcr_per_conflict  # noqa: E402

ARMS = ["random", "mg", "pd"]
EXCLUDING = "_excluding_out_of_limits"


def evaluated_sets(root):
    """Chunk ids of each test partition, keyed as `split_key` builds them."""
    sets = {}
    for f in (glob.glob(f"{root}/data/*_combination_testing.json")
              + glob.glob(f"{root}/data/dataset1_*_testing.json")):
        sets[os.path.basename(f)[:-len("_testing.json")]] = set(map(str, json.load(open(f))["chunk_id"]))
    return sets


def split_key(dataset, arm):
    return f"{dataset}_{arm}" if dataset == "dataset1" else f"{dataset}_{arm}_combination"


def load_mergegen(root, evaluated, column=SIM):
    """MergeGen's similarity per conflict, from `column` (the RQ4 draw passes `SIM_DRAW`)."""
    rows = []
    for s in glob.glob(f"{root}/mergeGen/JIT/*/model_*/similarities.csv"):
        folder = os.path.basename(os.path.dirname(os.path.dirname(s)))
        if "__test_" in folder:
            continue
        model = os.path.basename(os.path.dirname(s))[6:].rsplit("_", 1)[0]
        dataset, arm = folder.rsplit("_", 1)
        d = pd.read_csv(s, dtype={"chunk_id": str})
        d = d[d.chunk_id.isin(evaluated[split_key(dataset, arm)])]
        if column not in d.columns:
            raise RuntimeError(f"{s} has no column {column}. Run mergegen_similarity.py again.")
        d = d[["chunk_id", column, "exact_match_full"]]
        d.columns = ["chunk_id", "mergegen", "mergegen_em"]
        d["dataset"], d["arm"], d["model"] = dataset, arm, model
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def paired_rank_biserial(a, b):
    """Rank-biserial correlation for paired samples, the effect size of the Wilcoxon signed-rank
    test: (sum of positive ranks - sum of negative ranks) / total, ties discarded. From -1 (b
    always larger) to +1 (a always larger)."""
    d = (a - b)
    d = d[d != 0]
    if len(d) == 0:
        return 0.0
    ranks = d.abs().rank()
    return (ranks[d > 0].sum() - ranks[d < 0].sum()) / ranks.sum()


def paired_comparison(j, label):
    """Paired measures per conflict: SBCR wins, ties and losses, the paired rank-biserial and the
    Wilcoxon p, with the descriptive columns of each approach. Exact match is equality with the
    whole resolution, all whitespace removed."""
    rows = []
    for (dataset, arm), g in j.groupby(["dataset", "arm"]):
        _, p = wilcoxon(g.sbcr, g.mergegen)
        rows.append({"analysis": label, "dataset": dataset, "arm": arm, "n": len(g),
                     "out_of_limits": int(g.out_of_limits.sum()),
                     "sbcr": g.sbcr.mean(), "mergegen": g.mergegen.mean(),
                     "difference": g.sbcr.mean() - g.mergegen.mean(),
                     "sbcr_wins": (g.sbcr > g.mergegen).mean(),
                     "tie": (g.sbcr == g.mergegen).mean(),
                     "mergegen_wins": (g.sbcr < g.mergegen).mean(),
                     "rank_biserial": paired_rank_biserial(g.sbcr, g.mergegen),
                     "p": p,
                     "sbcr_sd": g.sbcr.std(), "sbcr_median": g.sbcr.median(), "sbcr_exact": g.sbcr_em.mean(),
                     "mergegen_sd": g.mergegen.std(), "mergegen_median": g.mergegen.median(),
                     "mergegen_exact": g.mergegen_em.mean()})
    return pd.DataFrame(rows)


def paired_frames(sb, mg):
    """SBCR per conflict joined to MergeGen on the same conflicts.

    Returns the RQ1/RQ2 frame (each dataset with its own model and configuration) and the RQ3
    frame (crossed between Dataset1 and Dataset2_Java: trained or tuned on the other dataset).
    """
    within = sb[~sb.target.str.startswith("rq3")]
    sbm = sbcr_per_conflict(within, ["target", "arm", "chunk_id"]).rename(columns={"target": "dataset"})
    j = sbm.merge(mg[mg.dataset == mg.model], on=["dataset", "arm", "chunk_id"])

    cross = sb[sb.target.str.startswith("rq3")].copy()
    cross["dataset"] = cross.target.map({"rq3_ds1": "dataset1", "rq3_java": "dataset2_Java"})
    sbc = sbcr_per_conflict(cross, ["dataset", "arm", "chunk_id"])
    j3 = sbc.merge(mg[mg.dataset != mg.model], on=["dataset", "arm", "chunk_id"])
    return j, j3


def with_sensitivity(j, label):
    """The comparison with out-of-limits conflicts scored 0, and without them."""
    return pd.concat([paired_comparison(j, label),
                      paired_comparison(j[~j.out_of_limits], label + EXCLUDING)], ignore_index=True)


def present_arms(t):
    """The arms present in the root, in the order of ARMS."""
    return [a for a in ARMS if a in set(t.arm)]


def show(t, column, title):
    print(f"\n--- {title} ---")
    print(t.pivot(index="dataset", columns="arm", values=column)[present_arms(t)].round(4).to_string())


def show_sensitivity(t, label):
    both = t[t.analysis == label].merge(t[t.analysis == label + EXCLUDING],
                                        on=["dataset", "arm"], suffixes=("", "_excl"))
    both = both[both.out_of_limits > 0]
    print(f"\n--- {label}: out-of-limits conflicts scored 0 vs. left out ---")
    if both.empty:
        print("no conflict above the limit")
        return
    both["change"] = both.difference - both.difference_excl
    print(both[["dataset", "arm", "n", "out_of_limits", "difference", "difference_excl", "change"]]
          .round(4).to_string(index=False))
    print(f"largest change in the mean difference: {both.change.abs().max():.4f}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--out", default=None, help="folder of the two CSVs; without it, the root itself")
    p.add_argument("--seeds", default=None, help="SBCR seeds to read, comma-separated; without it, all")
    args = p.parse_args()
    root = os.path.expanduser(args.root)
    out = root
    if args.out:
        out = os.path.expanduser(args.out)
        os.makedirs(out, exist_ok=True)
    seeds = [x.strip() for x in args.seeds.split(",") if x.strip()] if args.seeds else None
    evaluated = evaluated_sets(root)

    sb = load_sbcr_similarities(root, seeds=seeds)
    # Each arm's evaluations on its own test partition only. The common-set evaluations
    # (partition pd, arm random or mg) would otherwise count seed 3022024 twice.
    sb = sb[sb.partition == sb.arm]
    mg = load_mergegen(root, evaluated)

    per_seed = sb.groupby(["target", "arm", "seed"])[SIM].mean().reset_index()
    spread = per_seed.groupby(["target", "arm"])[SIM].agg(["mean", "std", "min", "max"])
    spread["amplitude"] = spread["max"] - spread["min"]
    spread.round(4).to_csv(f"{out}/seed_spread.csv")
    seeds = per_seed.seed.nunique()
    print(f"=== spread across the {seeds} seeds ===")
    if seeds > 1:
        print(f"largest standard deviation: {spread['std'].max():.4f}   largest range: {spread['amplitude'].max():.4f}")
    else:
        print("one seed only, no spread")

    j, j3 = paired_frames(sb, mg)

    t1 = with_sensitivity(j, "rq1_rq2")
    main1 = t1[t1.analysis == "rq1_rq2"]
    print("\n=== SBCR vs MergeGen: same conflicts, same metric ===")
    for column, title in [("sbcr", "SBCR"), ("mergegen", "MergeGen"),
                          ("difference", "SBCR − MergeGen"), ("sbcr_wins", "SBCR wins (share of conflicts)"),
                          ("tie", "tie"), ("mergegen_wins", "MergeGen wins"),
                          ("rank_biserial", "paired rank-biserial (+ favors SBCR)"),
                          ("sbcr_median", "SBCR median"), ("mergegen_median", "MergeGen median"),
                          ("sbcr_exact", "SBCR exact match (share of conflicts)"),
                          ("mergegen_exact", "MergeGen exact match (share of conflicts)")]:
        show(main1, column, title)
    print("\n--- p (paired Wilcoxon) ---")
    print(main1.pivot(index="dataset", columns="arm", values="p")[present_arms(main1)]
          .map(lambda x: f"{x:.1e}").to_string())
    show_sensitivity(t1, "rq1_rq2")

    t3 = with_sensitivity(j3, "rq3")
    main3 = t3[t3.analysis == "rq3"]
    print("\n=== RQ3: trained or tuned on the other dataset ===")
    for column, title in [("sbcr", "SBCR (crossed)"), ("mergegen", "MergeGen (crossed)"),
                          ("difference", "SBCR − MergeGen")]:
        show(main3, column, title)
    show_sensitivity(t3, "rq3")

    pd.concat([t1, t3]).to_csv(f"{out}/comparison.csv", index=False)
    print(f"\nwritten to {out}/comparison.csv")


if __name__ == "__main__":
    main()
