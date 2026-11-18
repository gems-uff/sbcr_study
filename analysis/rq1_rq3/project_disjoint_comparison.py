#!/usr/bin/env python3
"""The common set of `leakage_effect.py` with SBCR scored 0 above its size limit.

The comparison of SBCR and MergeGen on the test partition of `pd`, the project-disjoint arm,
restricted to the conflicts outside the training of the `random` and `mg` models, with SBCR
loaded through `sbcr_scores.load_sbcr_similarities`, so each `OUT_OF_LIMITS` conflict enters
with similarity 0 (`--out-of-limits exclude` leaves them out). Two paired changes of the gap
SBCR − MergeGen are tested with the Wilcoxon signed-rank test: `pd` minus `random` and `pd`
minus `mg`.

Inputs: the root of the three arms (`--root`) and, optionally, another root for `mg` (`--mg-root`).
Output: `<out>/common_set_current_rules.csv`.

    python analysis/rq1_rq3/project_disjoint_comparison.py --root <root of the three arms> \
        --mg-root <root of partition 1> --out <dir>
"""
import argparse
import os
import sys

import pandas as pd
from scipy.stats import wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from leakage_effect import (  # noqa: E402
    ARMS, DATASETS, ci95, mergegen_on_pd_test, partitions, pd_evaluated_test, seen)
from sbcr_scores import OUT_OF_LIMITS, SIM, load_sbcr_similarities  # noqa: E402
SEED = "3022024"


def sbcr_on_pd_test(root, mg_root, out_of_limits):
    sb = load_sbcr_similarities(root, out_of_limits=out_of_limits, seeds=[SEED])
    if mg_root:
        new = load_sbcr_similarities(mg_root, out_of_limits=out_of_limits, seeds=[SEED])
        sb = pd.concat([sb[sb.arm != "mg"], new[new.arm == "mg"]], ignore_index=True)
    sb = sb[(sb.partition == "pd") & (sb.seed == SEED) & (~sb.target.str.startswith("rq3"))]
    sb = sb.rename(columns={"target": "dataset", SIM: "sbcr"})
    sb["out_of_limits"] = sb.status == OUT_OF_LIMITS
    return sb[["dataset", "arm", "chunk_id", "sbcr", "out_of_limits"]]


def paired(a, b):
    change = a - b
    try:
        _, p = wilcoxon(a, b)
    except ValueError:
        p = float("nan")
    return change.mean(), ci95(change), p


def common_set(mg, sb, part, test, reference, rule):
    j = sb.merge(mg.rename(columns={SIM: "mergegen"})[["dataset", "arm", "chunk_id", "mergegen"]],
                 on=["dataset", "arm", "chunk_id"])
    j["gap"] = j.sbcr - j.mergegen
    rows = []
    for ds in DATASETS:
        clean = test[ds] - seen(part, "random", ds, reference) - seen(part, "mg", ds, reference)
        g = j[(j.dataset == ds) & (j.chunk_id.isin(clean))]
        w = g.pivot_table(index="chunk_id", columns="arm", values="gap")
        if not all(arm in w for arm in ARMS):
            rows.append({"rule": rule, "reference": reference, "dataset": ds, "n": 0})
            continue
        w = w[ARMS].dropna()
        ool = g[g.chunk_id.isin(w.index) & g.out_of_limits].chunk_id.nunique()
        row = {"rule": rule, "reference": reference, "dataset": ds, "n": len(w), "sbcr_out_of_limits": ool,
               "gap_random": w["random"].mean(), "gap_mg": w.mg.mean(), "gap_pd": w.pd.mean()}
        for other in ("random", "mg"):
            change, ci, p = paired(w.pd, w[other])
            row.update({f"change_pd_minus_{other}": change, f"ci95_pd_minus_{other}": ci,
                        f"p_pd_minus_{other}": p})
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--mg-root", default=None, help="root everything of the mg arm comes from")
    p.add_argument("--out-of-limits", choices=["zero", "exclude", "both"], default="both")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    root = os.path.expanduser(args.root)
    mg_root = os.path.expanduser(args.mg_root) if args.mg_root else None
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)
    rules = ["zero", "exclude"] if args.out_of_limits == "both" else [args.out_of_limits]

    part, test = partitions(root, mg_root), pd_evaluated_test(root)
    mg = mergegen_on_pd_test(root, mg_root)
    tables = []
    for rule in rules:
        sb = sbcr_on_pd_test(root, mg_root, rule)
        for reference in ("train", "train+validation"):
            tables.append(common_set(mg, sb, part, test, reference, rule))
    result = pd.concat(tables, ignore_index=True)
    pd.set_option("display.width", 250)
    print(result.round(4).to_string(index=False))
    result.to_csv(f"{out}/common_set_current_rules.csv", index=False)
    print(f"\nwritten to {out}/common_set_current_rules.csv")


if __name__ == "__main__":
    main()
