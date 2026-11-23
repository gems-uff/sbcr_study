#!/usr/bin/env python3
"""Compares a rerun of SBCR with the stored run: candidates and spreadsheet rows.

For an evaluation (`sbcr_evaluate.py`), each candidate of `OUTPUT/<chunk_id>` and each row of the
spreadsheet (fitness, similarity to the resolution, status) is compared with the stored one. For
a tuning (`sbcr_tuning.py`, which saves no candidate), each row of the rerun is matched with the
stored row of the same conflict and configuration. SBCR's search is bounded by wall-clock time, so
a conflict whose search reached its timeout can return another candidate on another machine or
under another load; the report gives the time of each differing row.

Inputs: the folder of the rerun (`--new`) and that of the stored run (`--stored`), each with
`RESULTS/*.xlsx`. Output: the report, on the standard output.

    python validation/compare_sbcr.py --new <smoke>/sbcr/eval_dataset1_mg_s3022024 \
        --stored <archives>/partition-1/sbcr/eval_dataset1_mg_s3022024
"""
import argparse
import glob
import os

import pandas as pd

KEYS_TUNING = ["chunk_id", "maximum_neighbors", "max_iterations_without_improvement", "ils_timeout"]


def sheet(folder):
    files = glob.glob(os.path.join(folder, "RESULTS", "*.xlsx"))
    if len(files) != 1:
        raise SystemExit(f"{folder}: expected one spreadsheet in RESULTS, found {len(files)}")
    df = pd.read_excel(files[0], engine="openpyxl")
    df["chunk_id"] = df["chunk_id"].astype(str)
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--new", required=True)
    p.add_argument("--stored", required=True)
    args = p.parse_args()

    new, old = sheet(args.new), sheet(args.stored)
    tuning = "ils_timeout" in new.columns
    keys = KEYS_TUNING if tuning else ["chunk_id"]
    for df in (new, old):
        for k in keys[1:]:
            df[k] = pd.to_numeric(df[k], errors="coerce")
    m = new.merge(old, on=keys, how="left", suffixes=("", "_stored"), indicator=True)
    print(f"{'tuning' if tuning else 'evaluation'}: {len(new)} rows in the rerun, "
          f"{(m['_merge'] == 'both').sum()} matched in the stored run of {len(old)} rows")
    m = m[m["_merge"] == "both"]

    same_sim = (m["solution_sim_lcs"].round(12) == m["solution_sim_lcs_stored"].round(12)) | \
        (m["solution_sim_lcs"].isna() & m["solution_sim_lcs_stored"].isna())
    same_status = m["status"].astype(str) == m["status_stored"].astype(str)
    print(f"  same status: {same_status.sum()}/{len(m)}")
    print(f"  same similarity to the resolution: {same_sim.sum()}/{len(m)}")
    if "fitness" in m:
        same_fit = (m["fitness"].round(12) == m["fitness_stored"].round(12)) | (m["fitness"].isna() & m["fitness_stored"].isna())
        print(f"  same fitness: {same_fit.sum()}/{len(m)}")

    if not tuning:
        equal = differ = missing = 0
        diff_ids = []
        for cid in m["chunk_id"]:
            a, b = os.path.join(args.new, "OUTPUT", cid), os.path.join(args.stored, "OUTPUT", cid)
            if not (os.path.exists(a) and os.path.exists(b)):
                missing += os.path.exists(a) != os.path.exists(b)
                continue
            if open(a, "rb").read() == open(b, "rb").read():
                equal += 1
            else:
                differ += 1
                diff_ids.append(cid)
        print(f"  candidates: {equal} equal, {differ} different, {missing} present on one side only")
        d = m[m["chunk_id"].isin(diff_ids)]
    else:
        d = m[~same_sim]
    if len(d):
        cols = keys + ["solution_sim_lcs", "solution_sim_lcs_stored", "time_seconds", "time_seconds_stored"]
        print("\nRows that differ:")
        print(d[cols].to_string(index=False))
        delta = (d["solution_sim_lcs"] - d["solution_sim_lcs_stored"]).abs()
        print(f"\n  largest difference of similarity: {delta.max():.4f}; "
              f"mean similarity of these rows {d['solution_sim_lcs'].mean():.4f} rerun, "
              f"{d['solution_sim_lcs_stored'].mean():.4f} stored")
    print(f"\n  mean similarity over the matched rows: {m['solution_sim_lcs'].mean():.6f} rerun, "
          f"{m['solution_sim_lcs_stored'].mean():.6f} stored")


if __name__ == "__main__":
    main()
