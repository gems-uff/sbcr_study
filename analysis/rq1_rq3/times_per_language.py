#!/usr/bin/env python3
"""Time per conflict of each approach, per dataset, on one root.

MergeGen: the per-step times of `mergegen/jit_inference.py`
(`mergeGen/JIT/<dataset>_<arm>/model_<dataset>_<arm>/times.csv`), with the dataset's own
model. Preprocessing is tokenization, `git merge-file` and the tensors; generation is the
model's `generate`; decoding turns the tokens back into text; end-to-end is the whole pass.

SBCR: `time_seconds` of the result spreadsheet of `sbcr/eval_<dataset>_<arm>_s<seed>`, which
times the search and the building of the candidate text. The conflicts above SBCR's
20,000-character limit have no time and are counted apart. The script counts the conflicts
whose time exceeds the timeout of the chosen configuration: `sbcr_evaluate.py` checks it
between iterations, so a run stops only after the iteration under way ends.

Two populations: the whole test partition (MergeGen only) and its combination subset, on which
the approaches are compared, there also per conflict over the conflicts SBCR processed: share
of conflicts in which SBCR is slower and faster, Wilcoxon signed-rank test and paired
rank-biserial correlation.

Checks, before the tables: the parts of each MergeGen row add up to its end-to-end time, the
sum of the end-to-end times does not exceed the wall time `mergeGen/LOGS/jit.log` records for
the run by more than 0.05 min (the log rounds it to 0.1 min), SBCR's times agree with
`sbcr_similarities.csv`, and their sum does not exceed the wall time of the evaluation in
`logs/sbcr_queue.csv`.

Inputs: the root (`--root`), with `chosen_configurations.csv`.
Output: `<root>/times_per_language.csv`, and the tables as Markdown on the standard output.

    python analysis/rq1_rq3/times_per_language.py --root <root> [--arm mg] [--seed 3022024]
"""
import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from compare_approaches import paired_rank_biserial  # noqa: E402
from sbcr_scores import OK, OUT_OF_LIMITS, sbcr_chunk_ids  # noqa: E402

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
PRE = ["tokenization", "git_merge", "tensors"]


def sbcr_configuration(root, name, arm):
    """(neighbors, stagnation iterations, timeout in seconds) chosen for the dataset, from
    `chosen_configurations.csv` (`sbcr/select_configuration.py`)."""
    c = pd.read_csv(f"{root}/chosen_configurations.csv")
    c = c[c.run == f"{name}_{arm}"]
    if len(c) != 1:
        raise SystemExit(f"{name}: {len(c)} rows for {name}_{arm} in chosen_configurations.csv")
    return tuple(int(v) for v in c.configuration.iloc[0].split(","))
def wall_minutes(root):
    """Wall time of each run of the dataset's own model, from `mergeGen/LOGS/jit.log`."""
    out = {}
    for line in open(f"{root}/mergeGen/LOGS/jit.log", encoding="utf-8"):
        m = re.match(r"(\S+) <- (\S+): (\d+) conflicts, ([\d.]+) min", line)
        if m and m.group(1) == m.group(2):
            out[m.group(1)] = float(m.group(4))
    return out


def sbcr_wall_hours(root, label):
    """Wall time of an SBCR evaluation, from its start and end events in `logs/sbcr_queue.csv`."""
    # the last field holds the configuration with unquoted commas, so it is split by hand
    lines = open(f"{root}/logs/sbcr_queue.csv", encoding="utf-8").read().splitlines()[1:]
    q = pd.DataFrame([line.split(",", 3)[:3] for line in lines], columns=["label", "event", "when"])
    q = q[q.label == label]
    start = pd.to_datetime(q[q.event == "start"].when).max()
    end = pd.to_datetime(q[q.event == "end"].when).max()
    return (end - start).total_seconds() / 3600


def load_mergegen(root, name, arm):
    t = pd.read_csv(f"{root}/mergeGen/JIT/{name}_{arm}/model_{name}_{arm}/times.csv", dtype={"chunk_id": str})
    t["preprocessing"] = t[PRE].sum(axis=1)
    parts = t.preprocessing + t.generation + t.decoding
    gap = (t.end_to_end - parts).abs().max()
    if gap > 1e-3:
        raise SystemExit(f"{name}: the parts differ from the end-to-end time by up to {gap:.4f} s")
    return t


def load_sbcr(root, name, arm, seed):
    folder = f"{root}/sbcr/eval_{name}_{arm}_s{seed}"
    d = pd.read_excel(glob.glob(f"{folder}/RESULTS/*.xlsx")[0], dtype={"chunk_id": str})
    d["status"] = d.status.astype(str)
    sb = pd.read_csv(f"{root}/sbcr_similarities.csv", dtype={"chunk_id": str, "seed": str})
    sb = sb[(sb.target == name) & (sb.arm == arm) & (sb.seed == seed) & (sb.partition == arm)]
    ok = d[d.status == OK].merge(sb[["chunk_id", "time"]], on="chunk_id", how="left")
    if ok.time.isna().any() or not np.allclose(ok.time_seconds.astype(float), ok.time):
        raise SystemExit(f"{name}: SBCR times differ from sbcr_similarities.csv")
    total, wall = ok.time_seconds.astype(float).sum() / 3600, sbcr_wall_hours(root, os.path.basename(folder))
    if total > wall:
        raise SystemExit(f"{name}: SBCR times add up to more than the wall time of the evaluation")
    print(f"{name}: SBCR times add up to {total:.2f} h, wall time of the evaluation {wall:.2f} h")
    return d


def describe(s):
    return {"mean": s.mean(), "median": s.median(), "p90": s.quantile(0.9), "max": s.max()}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--arm", default="mg")
    p.add_argument("--seed", default="3022024", help="SBCR seed")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    walls = wall_minutes(root)

    rows, checks = [], []
    for name in DATASETS:
        mg = load_mergegen(root, name, args.arm)
        sb = load_sbcr(root, name, args.arm, args.seed)
        comb = sbcr_chunk_ids(root, name, args.arm)
        config = sbcr_configuration(root, name, args.arm)
        total = mg.end_to_end.sum() / 60
        checks.append(f"{name}: {len(mg)} timed conflicts, sum of end-to-end {total:.1f} min, "
                      f"wall time in jit.log {walls.get(name, float('nan')):.1f} min")
        if name in walls and total > walls[name] + 0.05:
            raise SystemExit(f"{name}: the end-to-end times add up to more than the wall time")

        for population in ["test", "combination"]:
            m = mg if population == "test" else mg[mg.chunk_id.isin(comb)]
            row = {"dataset": name, "population": population, "n": len(m),
                   "pre_share_aggregate": m.preprocessing.sum() / m.end_to_end.sum(),
                   "pre_share_median": (m.preprocessing / m.end_to_end).median()}
            for col, label in [("preprocessing", "mg_pre"), ("generation", "mg_gen"),
                               ("decoding", "mg_dec"), ("end_to_end", "mg_e2e")]:
                row.update({f"{label}_{k}": v for k, v in describe(m[col]).items()})
            if population == "combination":
                s = sb[sb.chunk_id.isin(comb)]
                if set(s.chunk_id) != comb or len(m) != len(comb):
                    raise SystemExit(f"{name}: the timed conflicts do not cover the combination subset")
                ok = s[s.status == OK].assign(t=lambda x: x.time_seconds.astype(float))
                row.update({"sbcr_n": len(ok), "sbcr_out_of_limits": int((s.status == OUT_OF_LIMITS).sum()),
                            "sbcr_configuration": ", ".join(map(str, config)), "sbcr_timeout": config[2],
                            "sbcr_above_timeout": int((ok.t > config[2]).sum())})
                row.update({f"sbcr_{k}": v for k, v in describe(ok.t).items()})
                pair = ok[["chunk_id", "t"]].merge(m[["chunk_id", "end_to_end"]], on="chunk_id")
                row.update({"paired_n": len(pair),
                            "sbcr_slower_share": (pair.t > pair.end_to_end).mean(),
                            "sbcr_faster_share": (pair.t < pair.end_to_end).mean(),
                            "rank_biserial": paired_rank_biserial(pair.t, pair.end_to_end),
                            "wilcoxon_p": wilcoxon(pair.t, pair.end_to_end).pvalue})
            rows.append(row)

    table = pd.DataFrame(rows)
    table.to_csv(f"{root}/times_per_language.csv", index=False)
    print("\n".join(checks))

    ms = lambda v: f"{1000 * v:.1f}"  # noqa: E731
    for population in ["test", "combination"]:
        tp = table[table.population == population]
        print(f"\n## MergeGen, {population} population (ms per conflict, mean / median)\n")
        print("| dataset | n | preprocessing | generation | decoding | end-to-end | preprocessing share, "
              "aggregate | preprocessing share, median |")
        print("|---|---|---|---|---|---|---|---|")
        for r in tp.itertuples():
            print(f"| {r.dataset} | {r.n:,} | {ms(r.mg_pre_mean)} / {ms(r.mg_pre_median)} "
                  f"| {ms(r.mg_gen_mean)} / {ms(r.mg_gen_median)} | {ms(r.mg_dec_mean)} / {ms(r.mg_dec_median)} "
                  f"| {ms(r.mg_e2e_mean)} / {ms(r.mg_e2e_median)} | {100 * r.pre_share_aggregate:.1f}% "
                  f"| {100 * r.pre_share_median:.1f}% |")
    tp = table[table.population == "combination"]
    print("\n## Both approaches, combination population (seconds per conflict)\n")
    print("| dataset | MergeGen n | MergeGen mean | median | p90 | max | SBCR n | out of limits | SBCR mean "
          "| median | p90 | max | SBCR slower | paired rank-biserial | Wilcoxon p |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in tp.itertuples():
        print(f"| {r.dataset} | {r.n:,} | {r.mg_e2e_mean:.3f} | {r.mg_e2e_median:.3f} | {r.mg_e2e_p90:.3f} "
              f"| {r.mg_e2e_max:.3f} | {int(r.sbcr_n):,} | {int(r.sbcr_out_of_limits)} | {r.sbcr_mean:.3f} "
              f"| {r.sbcr_median:.3f} | {r.sbcr_p90:.3f} | {r.sbcr_max:.1f} | {100 * r.sbcr_slower_share:.1f}% "
              f"| {r.rank_biserial:+.2f} | {r.wilcoxon_p:.1e} |")
    print("\nSBCR configuration (neighbors, stagnation iterations, timeout in s), conflicts whose time "
          "exceeds the timeout, and share of the paired conflicts in which SBCR is faster:")
    for r in tp.itertuples():
        print(f"  {r.dataset}: ({r.sbcr_configuration}); {int(r.sbcr_above_timeout)} of {int(r.sbcr_n):,} "
              f"above {int(r.sbcr_timeout)} s; faster in {100 * r.sbcr_faster_share:.1f}%")
    print(f"  total above the timeout: {int(tp.sbcr_above_timeout.sum())} of {int(tp.sbcr_n.sum()):,}")


if __name__ == "__main__":
    main()
