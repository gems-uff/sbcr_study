#!/usr/bin/env python3
"""Effect of leakage on MergeGen, and the two approaches on a set of conflicts common to the three arms.

- **Leakage**: the MergeGen models of the `control` and `mg` arms evaluated on the test
  partition of `pd`, against the model of `pd` itself, restricted to the conflicts the other
  model did not see.
- **Common set**: the difference SBCR − MergeGen in the three arms, on the conflicts of the
  test partition of `pd` that none of the three models saw.

What counts as "seen": `--reference train` excludes the training partition of the other arm,
`train+validation` also its validation partition, which MergeGen uses to choose the epoch, and
`both` (the default) reports the two. The similarity is `sim_lcs_no_whitespace`. SBCR is read
from `sbcr_similarities.csv` as it is, so its conflicts above the size limit are left out
(`project_disjoint_comparison.py` scores them 0).

With `--mg-root`, everything of the `mg` arm (partitions, the model on the test of `pd`, and SBCR
with the configuration of `mg` on the test of `pd`) comes from that root, and the rest from
`--root`, which is only read.

Inputs: the root of the three arms (`--root`) and, optionally, another root for `mg`.
Outputs, in `--out` (or the root): `leakage_effect.csv` and `common_set.csv`.

    python analysis/rq1_rq3/leakage_effect.py --root <root of the three arms> --mg-root <root> --out <dir>
"""
import argparse
import glob
import json
import os
import re
import sys

import pandas as pd
from scipy.stats import wilcoxon

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "similarity"))
from sbcr_scores import SIM  # noqa: E402

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
ARMS = ["control", "mg", "pd"]


def partitions(root, mg_root=None):
    """{(arm, dataset): {"train": set, "validation": set}}"""
    p = {}
    for arm in ARMS:
        source = mg_root if (arm == "mg" and mg_root) else root
        for ds in DATASETS:
            a = pd.read_csv(f"{source}/data/split_{ds}_{arm}.csv", dtype={"chunk_id": str})
            p[(arm, ds)] = {k: set(a[a.partition == k].chunk_id) for k in ("train", "validation")}
    return p


def pd_evaluated_test(root):
    t = {}
    for ds in DATASETS:
        f = (f"{root}/data/{ds}_pd_testing.json" if ds == "dataset1"
             else f"{root}/data/{ds}_pd_combination_testing.json")
        t[ds] = set(map(str, json.load(open(f))["chunk_id"]))
    return t


def seen(part, arm, ds, reference):
    s = set(part[(arm, ds)]["train"])
    if reference == "train+validation":
        s |= part[(arm, ds)]["validation"]
    return s


def mergegen_on_pd_test(root, mg_root=None):
    """MergeGen's similarity on the test partition of pd, with the model of each arm."""
    rows = []
    files = glob.glob(f"{root}/mergeGen/JIT/*/model_*/similarities.csv")
    if mg_root:
        files = [f for f in files if not f.endswith("_mg/similarities.csv")]
        files += glob.glob(f"{mg_root}/mergeGen/JIT/*__test_pd/model_*_mg/similarities.csv")
    for s in files:
        folder = os.path.basename(os.path.dirname(os.path.dirname(s)))
        model, arm = os.path.basename(os.path.dirname(s))[6:].rsplit("_", 1)
        ds = re.sub(r"__test_pd$", "", folder).rsplit("_", 1)[0]
        if not (folder.endswith("__test_pd") or folder.endswith("_pd")) or ds != model:
            continue
        d = pd.read_csv(s, dtype={"chunk_id": str})[["chunk_id", SIM, "exact_match_full"]]
        d["dataset"], d["arm"] = ds, arm
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def ci95(x):
    return 1.96 * x.std() / len(x) ** 0.5 if len(x) > 1 else float("nan")


def leakage_analysis(mg, part, test, reference):
    rows = []
    for other in ("control", "mg"):
        for ds in DATASETS:
            eligible = test[ds] - seen(part, other, ds, reference)
            g = mg[(mg.dataset == ds) & (mg.chunk_id.isin(eligible))]
            w = g.pivot_table(index="chunk_id", columns="arm", values=SIM)
            if other not in w or "pd" not in w:
                continue
            w = w[[other, "pd"]].dropna()
            e = g.pivot_table(index="chunk_id", columns="arm", values="exact_match_full")[[other, "pd"]].dropna()
            diff = w[other] - w.pd
            try:
                _, p = wilcoxon(w[other], w.pd)
            except ValueError:
                p = float("nan")
            rows.append({"reference": reference, "comparison": f"{other} vs pd", "dataset": ds,
                         "n": len(w), "sim_other": w[other].mean(), "sim_pd": w.pd.mean(),
                         "difference": diff.mean(), "ci95": ci95(diff), "p": p,
                         "em_other": e[other].mean(), "em_pd": e.pd.mean()})
    return pd.DataFrame(rows)


def common_set_analysis(mg, sb, part, test, reference):
    sbp = sb[(sb.partition == "pd") & (sb.seed == "3022024") & (~sb.target.str.startswith("rq3"))]
    sbp = sbp.rename(columns={"target": "dataset", SIM: "sbcr"})[["dataset", "arm", "chunk_id", "sbcr"]]
    j = sbp.merge(mg.rename(columns={SIM: "mergegen"})[["dataset", "arm", "chunk_id", "mergegen"]],
                  on=["dataset", "arm", "chunk_id"])
    j["gap"] = j.sbcr - j.mergegen
    rows = []
    for ds in DATASETS:
        clean = test[ds] - seen(part, "control", ds, reference) - seen(part, "mg", ds, reference)
        w = j[(j.dataset == ds) & (j.chunk_id.isin(clean))].pivot_table(
            index="chunk_id", columns="arm", values="gap")
        if not all(arm in w for arm in ARMS):
            rows.append({"reference": reference, "dataset": ds, "n": 0})
            continue
        w = w[ARMS].dropna()
        change = w.pd - w.control
        try:
            _, p = wilcoxon(w.pd, w.control)
        except ValueError:
            p = float("nan")
        rows.append({"reference": reference, "dataset": ds, "n": len(w),
                     "gap_control": w.control.mean(), "gap_mg": w.mg.mean(), "gap_pd": w.pd.mean(),
                     "change_pd_minus_control": change.mean(), "ci95": ci95(change), "p": p})
    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--reference", choices=["train", "train+validation", "both"], default="both")
    p.add_argument("--mg-root", default=None, help="root everything of the mg arm comes from")
    p.add_argument("--out", default=None, help="folder of the tables; without it, --root itself")
    args = p.parse_args()
    root = os.path.expanduser(args.root)
    mg_root = os.path.expanduser(args.mg_root) if args.mg_root else None
    out = os.path.expanduser(args.out) if args.out else root
    os.makedirs(out, exist_ok=True)
    refs = ["train", "train+validation"] if args.reference == "both" else [args.reference]

    part, test = partitions(root, mg_root), pd_evaluated_test(root)
    mg = mergegen_on_pd_test(root, mg_root)
    sb = pd.read_csv(f"{root}/sbcr_similarities.csv", dtype={"chunk_id": str, "seed": str})
    if mg_root:
        new = pd.read_csv(f"{mg_root}/sbcr_similarities.csv", dtype={"chunk_id": str, "seed": str})
        sb = pd.concat([sb[sb.arm != "mg"], new[new.arm == "mg"]], ignore_index=True)

    pd.set_option("display.width", 220)
    leak = pd.concat([leakage_analysis(mg, part, test, r) for r in refs], ignore_index=True)
    common = pd.concat([common_set_analysis(mg, sb, part, test, r) for r in refs], ignore_index=True)

    print("=== leakage ===")
    print(leak.round(4).to_string(index=False))
    print("\n=== common set ===")
    print(common.round(4).to_string(index=False))

    leak.to_csv(f"{out}/leakage_effect.csv", index=False)
    common.to_csv(f"{out}/common_set.csv", index=False)
    print(f"\nwritten to {out}/leakage_effect.csv, common_set.csv")


if __name__ == "__main__":
    main()
