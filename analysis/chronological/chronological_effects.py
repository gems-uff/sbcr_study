#!/usr/bin/env python3
"""Effect of chronology on each tool: training only on the past, and drift over the test period.

(a) Training only on the past. On the same conflicts, each tool of the chronological split,
    trained or tuned only on merges older than the test, against the same tool of each of the
    three partitions of the merge-grouped design, whose random assignment mixes past and future.
    For each reference, the conflicts are the evaluated chronological test conflicts that were
    not in that reference's training, so neither model saw them; the references' side comes from
    `chronological_references.py`. Per dataset, tool and reference: the paired difference
    chronological − reference, its 95% interval (normal approximation), the test chosen by the
    normality of the paired differences (Shapiro-Wilk: the paired t-test with Cohen's d_z, or the
    Wilcoxon signed-rank test with the paired rank-biserial correlation), Holm's correction over
    all the tests and, apart, over the ten against the first reference; and the difference SBCR −
    MergeGen under each condition, with a summary over the three references.

(b) Drift. For each evaluated chronological test conflict, the days between its merge and the
    test cut of its dataset. Per dataset and tool: the Spearman correlation between days and
    similarity, with Holm's correction over the ten tests, and the mean similarity per third of
    the test period. The correlation of the difference SBCR − MergeGen with the days is reported
    outside the correction.

Whole test sets: every evaluated test conflict of the chronological split against every one of
the main split (the first reference), as independent samples (Welch's t-test with Cohen's d, or
the Mann-Whitney U test with the rank-biserial correlation, by Shapiro-Wilk), with Holm over the
ten tests. The two sets hold mostly different conflicts, so a difference here mixes the training
with the composition of the tests.

SBCR scores 0 above its size limit. Also a library: `holm` is imported by `rq3_gaps.py`.

Inputs: the chronological root (`--root`), the references (`--ref`), `commit_dates.csv` (`--dates`)
and the datasets (`--data-root`).
Outputs, in `--out`: `training_on_past.csv`, `whole_test_sets.csv`, `training_on_past_summary.csv`,
`gap_by_condition.csv`, `drift.csv`, `drift_by_third.csv`, `chrono_conflicts.csv` and
`chrono_effects.json` (parameters and hashes).

    python analysis/chronological/chronological_effects.py --root <chronological root> \
        --ref p1=<partition 1 root> --ref p2=<partition 2 root> --ref p3=<partition 3 root> \
        --dates <dir>/commit_dates.csv --data-root <data> --out <dir>
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, shapiro, spearmanr, ttest_ind, ttest_rel, wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "rq1_rq3"))
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "preparation"))
from compare_approaches import evaluated_sets, load_mergegen, paired_frames, paired_rank_biserial  # noqa: E402
from sbcr_scores import OK, OUT_OF_LIMITS, SIM, load_sbcr_similarities  # noqa: E402
from sbcr_similarity import gestalt, normalize  # noqa: E402
from chronological_split import load_dates  # noqa: E402

sys.path.insert(0, HERE)
from temporal_structure import chunk_merges  # noqa: E402
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mergegen_ref(root, ref, dataset):
    """MergeGen of a reference partition on the chronological test, per conflict."""
    d = pd.read_csv(os.path.join(root, "mergeGen", "JIT", f"{dataset}_{ref}__test_mg", f"model_{dataset}_{ref}",
                                 "similarities.csv"), dtype={"chunk_id": str})
    return d.set_index("chunk_id")[SIM]


def sbcr_ref(root, ref, dataset):
    """SBCR with a reference's configuration on the chronological test, per conflict, 0 above its limit."""
    folder = os.path.join(root, "sbcr", f"eval_{ref}cfg_{dataset}")
    sheet = pd.read_excel(glob.glob(os.path.join(folder, "RESULTS", "*.xlsx"))[0], dtype={"chunk_id": str})
    data = json.load(open(os.path.join(root, "data", f"{dataset}.json")))
    resolution = {str(c): r for c, r in zip(data["chunk_id"], data["all_raw_res"])}
    out = {}
    for r in sheet.itertuples():
        if r.status == OUT_OF_LIMITS:
            out[r.chunk_id] = 0.0
        elif r.status == OK and os.path.exists(os.path.join(folder, "OUTPUT", r.chunk_id)):
            cand = open(os.path.join(folder, "OUTPUT", r.chunk_id), encoding="utf-8", errors="replace").read()
            # all whitespace removed, as in `sim_lcs_no_whitespace`
            out[r.chunk_id] = gestalt(normalize(cand), normalize(resolution[r.chunk_id]))
    return pd.Series(out)


def holm(p):
    """Holm-adjusted p-values, in the order given."""
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adjusted[i] = running
    return adjusted


def paired(a, b):
    """Paired test of a against b, chosen by the normality of the differences.

    Shapiro-Wilk on the paired differences first. If it does not reject normality
    (p >= 0.05), the paired t-test, with Cohen's d for paired samples (d_z, the mean
    difference over the standard deviation of the differences) as effect size.
    Otherwise the Wilcoxon signed-rank test, with the paired rank-biserial correlation
    as effect size. The effect size is computed for every test, and read only where the
    test rejects.
    """
    d = a - b
    shapiro_p = shapiro(d).pvalue if d.nunique() > 2 else 0.0
    if shapiro_p >= 0.05:
        test, p = "paired t", ttest_rel(a, b).pvalue
        measure, effect = "d_z", d.mean() / d.std(ddof=1)
    else:
        test, p = "Wilcoxon", (wilcoxon(a, b).pvalue if (d != 0).any() else 1.0)
        measure, effect = "rank-biserial", paired_rank_biserial(a, b)
    return {"mean_difference": d.mean(), "ci95": 1.96 * d.std(ddof=1) / np.sqrt(len(d)), "shapiro_p": shapiro_p,
            "test": test, "p": p, "effect_measure": measure, "effect_size": effect}


def independent(a, b):
    """Test of a against b as independent samples, chosen by the normality of each.

    Shapiro-Wilk on each sample. If neither rejects normality (p >= 0.05), Welch's t-test,
    with Cohen's d (pooled standard deviation) as effect size. Otherwise the Mann-Whitney U
    test, with the rank-biserial correlation 1 - 2U/(n_a n_b), equal to Cliff's delta, as
    effect size, positive when a tends to be larger. The effect size is read only where the
    test rejects.
    """
    shapiro_a, shapiro_b = shapiro(a).pvalue, shapiro(b).pvalue
    if min(shapiro_a, shapiro_b) >= 0.05:
        test, p = "Welch t", ttest_ind(a, b, equal_var=False).pvalue
        pooled = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
        measure, effect = "Cohen's d", (a.mean() - b.mean()) / pooled
    else:
        u = mannwhitneyu(b, a, alternative="two-sided")
        test, p = "Mann-Whitney", u.pvalue
        measure, effect = "rank-biserial", 1 - 2 * u.statistic / (len(a) * len(b))
    return {"shapiro_p_chronological": shapiro_a, "shapiro_p_main": shapiro_b, "test": test, "p": p,
            "effect_measure": measure, "effect_size": effect}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True)
    ap.add_argument("--ref", action="append", required=True, help="<label>=<root> of a reference partition")
    ap.add_argument("--dates", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root, out = (os.path.abspath(os.path.expanduser(x)) for x in (args.root, args.out))
    refs = [(r.split("=", 1)[0], os.path.abspath(os.path.expanduser(r.split("=", 1)[1]))) for r in args.ref]
    os.makedirs(out, exist_ok=True)

    evaluated = evaluated_sets(root)
    sb = load_sbcr_similarities(root)
    sb = sb[sb.partition == sb.arm]
    pairs, _ = paired_frames(sb, load_mergegen(root, evaluated))
    pairs = pairs[pairs.arm == "mg"]

    dates = load_dates(os.path.expanduser(args.dates))
    merges = chunk_merges(Path(os.path.expanduser(args.data_root)))
    cuts = json.load(open(os.path.join(root, "splits", "chrono_split.json")))["cuts"]

    on_past, gaps, drift, thirds, conflicts = [], [], [], [], []
    for name in DATASETS:
        p = pairs[pairs.dataset == name].set_index("chunk_id")
        for ref, ref_root in refs:
            split = pd.read_csv(os.path.join(ref_root, "splits", "mg", f"{name}.csv"), dtype={"chunk_id": str})
            p[f"{ref}_partition"] = p.index.map(dict(zip(split.chunk_id, split.partition)))
            p[f"mergegen_{ref}"] = mergegen_ref(root, ref, name).reindex(p.index)
            p[f"sbcr_{ref}"] = sbcr_ref(root, ref, name).reindex(p.index)
        key = {c: f"{r}@{h}" for c, (r, h) in merges[name].items()}
        p["date"] = pd.to_datetime(p.index.map(lambda c: dates.get(key.get(c))), utc=True)
        p["days_after_cut"] = (p.date - pd.Timestamp(cuts[name]["test_from"])).dt.days
        conflicts.append(p.reset_index().assign(dataset=name))

        # (a) for each reference, the conflicts neither model trained on
        for ref, _ in refs:
            s = p[p[f"{ref}_partition"].isin(["validation", "test"])]
            missing = s[[f"mergegen_{ref}", f"sbcr_{ref}"]].isna().any(axis=1).sum()
            if missing:
                sys.exit(f"{name}, {ref}: {missing} conflicts without the reference's result")
            for tool in ("mergegen", "sbcr"):
                on_past.append({"dataset": name, "tool": {"mergegen": "MergeGen", "sbcr": "SBCR"}[tool],
                                "reference": ref, "n": len(s), "chronological": s[tool].mean(),
                                "reference_mean": s[f"{tool}_{ref}"].mean(), **paired(s[tool], s[f"{tool}_{ref}"])})
            for condition, sbcr_col, mg_col in [("chronological", "sbcr", "mergegen"),
                                                (ref, f"sbcr_{ref}", f"mergegen_{ref}")]:
                gaps.append({"dataset": name, "reference": ref, "condition": condition, "n": len(s),
                             "sbcr": s[sbcr_col].mean(), "mergegen": s[mg_col].mean(),
                             "difference": s[sbcr_col].mean() - s[mg_col].mean(),
                             "mergegen_wins": (s[sbcr_col] < s[mg_col]).mean()})

        # (b) drift over the chronological test
        t = p.dropna(subset=["days_after_cut"])
        for tool, col in [("MergeGen", "mergegen"), ("SBCR", "sbcr")]:
            rho, pval = spearmanr(t.days_after_cut, t[col])
            drift.append({"dataset": name, "tool": tool, "n": len(t), "days_max": int(t.days_after_cut.max()),
                          "spearman_days_similarity": rho, "p": pval})
        rho, pval = spearmanr(t.days_after_cut, t.sbcr - t.mergegen)
        drift.append({"dataset": name, "tool": "SBCR − MergeGen", "n": len(t), "days_max": int(t.days_after_cut.max()),
                      "spearman_days_similarity": rho, "p": pval})
        t = t.assign(third=pd.qcut(t.days_after_cut.rank(method="first"), 3, labels=[1, 2, 3]).astype(int))
        for third, g in t.groupby("third"):
            thirds.append({"dataset": name, "third": third, "n": len(g), "days_from": int(g.days_after_cut.min()),
                           "days_to": int(g.days_after_cut.max()), "mergegen": g.mergegen.mean(), "sbcr": g.sbcr.mean(),
                           "difference": (g.sbcr - g.mergegen).mean()})

    on_past = pd.DataFrame(on_past)
    on_past["p_holm"] = holm(on_past.p)
    on_past["excludes_zero_holm"] = on_past.p_holm < 0.05
    # Against partition 1 alone, the main split of the paper: Holm over its ten tests.
    main = on_past.reference == refs[0][0]
    on_past.loc[main, "p_holm_main_split"] = holm(on_past.loc[main, "p"])
    summary_a = (on_past.groupby(["dataset", "tool"])
                 .agg(mean_difference=("mean_difference", "mean"), min_difference=("mean_difference", "min"),
                      max_difference=("mean_difference", "max"),
                      same_sign=("mean_difference", lambda d: bool((d > 0).all() or (d < 0).all())),
                      all_excluding_zero=("excludes_zero_holm", "all"))
                 .reset_index())
    drift = pd.DataFrame(drift)
    tools = drift.tool != "SBCR − MergeGen"
    drift.loc[tools, "p_holm"] = holm(drift.loc[tools, "p"])
    # Whole test sets: every evaluated test conflict of the chronological split against every
    # evaluated test conflict of the first reference (the main split), as independent samples.
    # The two sets hold mostly different conflicts, so a difference mixes the training with
    # the composition of the tests.
    ref_label, ref_root = refs[0]
    rsb = load_sbcr_similarities(ref_root)
    rsb = rsb[rsb.partition == rsb.arm]
    ref_pairs, _ = paired_frames(rsb, load_mergegen(ref_root, evaluated_sets(ref_root)))
    ref_pairs = ref_pairs[ref_pairs.arm == "mg"]
    whole = []
    for name in DATASETS:
        c = pairs[pairs.dataset == name]
        m = ref_pairs[ref_pairs.dataset == name]
        shared = len(set(c.chunk_id) & set(m.chunk_id))
        for tool, col in [("MergeGen", "mergegen"), ("SBCR", "sbcr")]:
            whole.append({"dataset": name, "tool": tool, "n_chronological": len(c), "n_main": len(m),
                          "shared_conflicts": shared, "chronological": c[col].mean(), "main": m[col].mean(),
                          "difference": c[col].mean() - m[col].mean(),
                          **independent(c[col].reset_index(drop=True), m[col].reset_index(drop=True))})
    whole = pd.DataFrame(whole)
    whole["p_holm"] = holm(whole.p)

    tables = {"training_on_past.csv": on_past, "whole_test_sets.csv": whole, "training_on_past_summary.csv": summary_a,
              "gap_by_condition.csv": pd.DataFrame(gaps), "drift.csv": drift, "drift_by_third.csv": pd.DataFrame(thirds),
              "chrono_conflicts.csv": pd.concat(conflicts, ignore_index=True)}
    pd.set_option("display.width", 200)
    for fname, t in tables.items():
        t.to_csv(os.path.join(out, fname), index=False)
        if fname != "chrono_conflicts.csv":
            print(f"\n=== {fname} ===\n{t.round(4).to_string(index=False)}")
    summary = {"root": root, "references": dict(refs), "dates": {args.dates: sha256(os.path.expanduser(args.dates))},
               "outputs": {f: sha256(os.path.join(out, f)) for f in tables}}
    json.dump(summary, open(os.path.join(out, "chrono_effects.json"), "w"), indent=2)
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
