#!/usr/bin/env python3
"""Tables of the population counts of one root, from `population_tokens.py` and `population_candidates.py`.

Per dataset of one arm, over two populations: `test`, the whole test partition, on which
MergeGen runs, and `combination`, its combination subset, on which the approaches are compared.
SBCR is counted only on the combination subset. Its empty candidates are split into the
conflicts above its 20,000-character limit and the empty candidates among those it processed,
whose ids are printed. An empty MergeGen candidate is an exact match when the resolution is
empty too.

Before tabulating, the exact match is checked against the similarity files (a similarity of 1
in `sbcr_scores.SIM`, and `exact_match_full`), and the empty flags of the two population CSVs
against each other. The script stops on any disagreement.

Input: the root (`--root`). Output: `<root>/population_table.csv`, and the tables as Markdown.

    python analysis/datasets/tabulate_population.py --root <root> [--arm mg] [--seed 3022024]
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "similarity"))
from sbcr_scores import OK, OUT_OF_LIMITS, SIM, sbcr_chunk_ids  # noqa: E402
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]


def as_bool(s):
    return s.astype(str).str.lower() == "true"


def check_exact_match(root, arm, seed, cand):
    """Exact match of the candidates CSV against `SIM == 1` and `exact_match_full`."""
    problems = []
    for name in DATASETS:
        sim = pd.read_csv(f"{root}/mergeGen/JIT/{name}_{arm}/model_{name}_{arm}/similarities.csv",
                          dtype={"chunk_id": str}, float_precision="round_trip")
        mg = cand[(cand.dataset == name) & (cand.approach == "mergegen")].merge(sim, on="chunk_id")
        problems.append((name, "mergegen", len(mg),
                         int((mg.exact_match != (mg[SIM] == 1.0)).sum()),
                         int((mg.exact_match != (mg.exact_match_full == 1.0)).sum())))
    sb = pd.read_csv(f"{root}/sbcr_similarities.csv", dtype={"chunk_id": str, "seed": str},
                     float_precision="round_trip")
    sb = sb[(sb.arm == arm) & (sb.seed == seed) & (sb.partition == arm)]
    for name in DATASETS:
        s = cand[(cand.dataset == name) & (cand.approach == "sbcr") & (cand.status == OK)]
        s = s.merge(sb[sb.target == name], on="chunk_id")
        problems.append((name, "sbcr", len(s),
                         int((s.exact_match != (s[SIM] == 1.0)).sum()),
                         int((s.exact_match != (s.exact_match_full == 1.0)).sum())))
    print("exact match against the similarity files (rows compared, differences from SIM == 1, "
          "differences from exact_match_full):")
    for p in problems:
        print("  ", p)
    if any(p[3] or p[4] for p in problems):
        raise SystemExit("the exact match disagrees with the similarity files")


def pct(k, n):
    return f"{k:,} ({100 * k / n:.1f}%)" if n else "–"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--arm", default="mg")
    p.add_argument("--seed", default="3022024", help="SBCR seed")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))

    tok = pd.read_csv(f"{root}/population_tokens.csv", dtype={"chunk_id": str})
    tok = tok[tok.arm == args.arm]
    for c in ["input_above_500", "resolution_above_200", "candidate_mergegen_empty", "candidate_mergegen_truncated"]:
        tok[c] = as_bool(tok[c])
    cand = pd.read_csv(f"{root}/population_candidates.csv",
                       dtype={"chunk_id": str, "seed": str, "status": str}, keep_default_na=False)
    cand = cand[(cand.arm == args.arm) & ((cand.approach == "mergegen") | (cand.seed == args.seed))]
    cand["empty"] = as_bool(cand.empty)
    cand["exact_match"] = as_bool(cand.exact_match)

    mg = cand[cand.approach == "mergegen"].merge(
        tok[["dataset", "chunk_id", "candidate_mergegen_empty"]], on=["dataset", "chunk_id"], how="outer",
        indicator=True)
    if (mg._merge != "both").any() or (mg["empty"] != mg.candidate_mergegen_empty).any():
        raise SystemExit("the MergeGen rows of the two population CSVs do not match")
    check_exact_match(root, args.arm, args.seed, cand)

    rows, empty_sbcr = [], {}
    for name in DATASETS:
        comb = sbcr_chunk_ids(root, name, args.arm)
        for population in ["test", "combination"]:
            t = tok[tok.dataset == name]
            m = cand[(cand.dataset == name) & (cand.approach == "mergegen")]
            s = cand[(cand.dataset == name) & (cand.approach == "sbcr")]
            if population == "combination":
                t, m = t[t.chunk_id.isin(comb)], m[m.chunk_id.isin(comb)]
                if set(s.chunk_id) != comb:
                    raise SystemExit(f"{name}: SBCR rows do not cover the combination subset")
            m_full = m[~m["empty"]]
            row = {"dataset": name, "population": population, "n": len(t),
                   "input_above_500": int(t.input_above_500.sum()),
                   "resolution_above_200": int(t.resolution_above_200.sum()),
                   "mergegen_truncated": int(t.candidate_mergegen_truncated.sum()),
                   "mergegen_empty": int(m["empty"].sum()),
                   "mergegen_empty_exact_match": int((m["empty"] & m.exact_match).sum()),
                   "mergegen_exact_match": int(m.exact_match.sum()),
                   "mergegen_nonempty": len(m_full),
                   "mergegen_only_v1v2": int((m_full.formed_only_v1v2.astype(str) == "True").sum())}
            if population == "combination":
                ok = s[s.status == OK]
                s_full = s[~s["empty"]]
                empty_sbcr[name] = sorted(ok[ok["empty"]].chunk_id)
                row.update({"sbcr_n": len(s),
                            "sbcr_out_of_limits": int((s.status == OUT_OF_LIMITS).sum()),
                            "sbcr_other_status": int((~s.status.isin([OK, OUT_OF_LIMITS])).sum()),
                            "sbcr_processed": len(ok),
                            "sbcr_empty_processed": int(ok["empty"].sum()),
                            "sbcr_exact_match": int(s.exact_match.sum()),
                            "sbcr_nonempty": len(s_full),
                            "sbcr_only_v1v2": int((s_full.formed_only_v1v2.astype(str) == "True").sum())})
            rows.append(row)
    table = pd.DataFrame(rows)
    table = table.astype({c: "Int64" for c in table.columns if c.startswith("sbcr_")})
    table.to_csv(f"{root}/population_table.csv", index=False)

    for population in ["test", "combination"]:
        tp = table[table.population == population]
        print(f"\n## MergeGen, {population} population\n")
        print("| dataset | n | input > 500 | resolution > 200 | truncated | empty | exact match | "
              "non-empty | only V1/V2 lines |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in tp.itertuples():
            print(f"| {r.dataset} | {r.n:,} | {pct(r.input_above_500, r.n)} | {pct(r.resolution_above_200, r.n)} "
                  f"| {pct(r.mergegen_truncated, r.n)} | {pct(r.mergegen_empty, r.n)} "
                  f"| {pct(r.mergegen_exact_match, r.n)} | {r.mergegen_nonempty:,} "
                  f"| {pct(r.mergegen_only_v1v2, r.mergegen_nonempty)} |")
        print("\nEmpty MergeGen candidates that are exact matches (the developers' resolution is empty too):")
        for r in tp.itertuples():
            print(f"  {r.dataset}: {r.mergegen_empty_exact_match:,} of {r.mergegen_empty:,}")
    tp = table[table.population == "combination"]
    print("\n## SBCR, combination population\n")
    print("| dataset | n | out of limits | other status | empty (processed) | exact match | non-empty "
          "| only V1/V2 lines |")
    print("|---|---|---|---|---|---|---|---|")
    for r in tp.itertuples():
        print(f"| {r.dataset} | {r.sbcr_n:,} | {pct(r.sbcr_out_of_limits, r.sbcr_n)} | {r.sbcr_other_status} "
              f"| {pct(r.sbcr_empty_processed, r.sbcr_processed)} | {pct(r.sbcr_exact_match, r.sbcr_n)} "
              f"| {r.sbcr_nonempty:,} | {pct(r.sbcr_only_v1v2, r.sbcr_nonempty)} |")
    print("\nEmpty SBCR candidates among the chunks it processed:")
    for name, ids in empty_sbcr.items():
        print(f"  {name}: {', '.join(ids) if ids else 'none'}")


if __name__ == "__main__":
    main()
