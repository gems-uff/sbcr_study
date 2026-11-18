#!/usr/bin/env python3
"""Two checks of the RQ4 results on the join of the labels at scale.

Both read `joined.csv` of `join_scale.py`, which joins the annotator's codes with the band and the
tool of each case.

1. **F5 and FN against MergeGen's limits.** In the clear SBCR win band, the conflicts coded F5
   (candidate cut off before the end) and FN (no candidate) are crossed with `population_tokens.csv`
   (arm `mg`): input above 500 tokens, resolution above 200 tokens, and MergeGen candidate at the
   400-token ceiling.
2. **The "neither, different similarities" cell of the near-tie band.** The conflicts in which the
   annotator read neither candidate as further (`further_annotator` equal or unclear) while the
   similarities differ (`further_measured` sbcr or mergegen), split by candidate code, FD (no
   difference between the candidates) or FU (neither clearly further).

Outputs, in `--out`: `f5_fn_limits.csv`, `f5_fn_limits_cases.csv`, `neither_different_similarities.csv`
and `neither_different_similarities_cases.csv`.

    python analysis/rq4/band_code_checks.py --joined <join folder>/joined.csv \
        --tokens <root of partition 1>/population_tokens.csv --out <dir>
"""
import argparse
import os

import pandas as pd

LIMITS = ["input_above_500", "resolution_above_200", "candidate_mergegen_truncated"]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--joined", required=True)
    p.add_argument("--tokens", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)

    j = pd.read_csv(os.path.expanduser(args.joined), dtype={"chunk_id": str})
    t = pd.read_csv(os.path.expanduser(args.tokens), dtype={"chunk_id": str})
    t = t[t.arm == "mg"]

    sbcr_band = j[(j.band == "sbcr") & (j.code_cand.isin(["F5", "FN"]))]
    m = sbcr_band.merge(t, on=["dataset", "chunk_id"], how="left", validate="one_to_one")
    missing = int(m.input_tokens.isna().sum())
    if missing:
        raise RuntimeError(f"{missing} conflicts of the band are not in {args.tokens}")
    rows = []
    for code, g in m.groupby("code_cand"):
        row = {"code": code, "conflicts": len(g), "missing_in_tokens": int(g.input_tokens.isna().sum())}
        row.update({c: int(g[c].astype(bool).sum()) for c in LIMITS})
        row["any_of_the_three"] = int(g[LIMITS].astype(bool).any(axis=1).sum())
        row["mergegen_candidate_empty"] = int(g.candidate_mergegen_empty.astype(bool).sum())
        rows.append(row)
    limits = pd.DataFrame(rows)
    limits.to_csv(f"{out}/f5_fn_limits.csv", index=False)
    m[["case", "dataset", "chunk_id", "code_cand", "empty_candidate_tool", "input_tokens", "resolution_tokens",
       "candidate_mergegen_tokens", "candidate_mergegen_empty"] + LIMITS].to_csv(
        f"{out}/f5_fn_limits_cases.csv", index=False)
    print("=== 1. F5 and FN in the clear SBCR win band, against MergeGen's limits ===")
    print(limits.to_string(index=False))

    tie = j[j.band == "tie"]
    cell = tie[tie.further_annotator.isin(["equal", "unclear"]) & tie.further_measured.isin(["sbcr", "mergegen"])]
    split = pd.crosstab(cell.code_cand, cell.further_measured, margins=True, margins_name="total")
    split.to_csv(f"{out}/neither_different_similarities.csv")
    cell[["case", "dataset", "chunk_id", "sim_sbcr", "sim_mergegen", "further_measured", "code_cand"]].to_csv(
        f"{out}/neither_different_similarities_cases.csv", index=False)
    print("\n=== 2. near tie, annotator reads neither as further, similarities differ ===")
    print("(columns: tool with the lower similarity)")
    print(split.to_string())


if __name__ == "__main__":
    main()
