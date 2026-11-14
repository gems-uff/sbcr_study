#!/usr/bin/env python3
"""Draws the RQ4 sample: 150 cases in three bands, 10 pilot cases, three blocks.

Frame. In each dataset, the conflicts of the combination subset of the `mg` test partition of
partition 1, with the SBCR candidate of seed 3022024 and the candidate of the MergeGen model
trained on the same dataset. A conflict above SBCR's 20,000-character limit has no SBCR candidate
and scores 0 for SBCR, so it stays in the frame, flagged in the sealed file. A frame of another
size than `EXPECTED_FRAME` stops the script.

Variable. `d = Sim_SBCR - Sim_MergeGen`, with `sim_lcs_full` (spaces and line breaks removed), the
column the draw ran with. The analyses recompute the bands with `sim_lcs_no_whitespace` when the
labels are joined to band and tool (`join_scale.py`).

Bands, per dataset, with `numpy.quantile` (linear interpolation):
- `sbcr`: d > 0 and d >= Q3 of the positive values;
- `mergegen`: d < 0 and |d| >= Q3 of |d| over the negative values;
- `tie`: |d| <= Q1 of |d| over the whole frame, exact ties included.
A conflict in a clear-win band and in the tie band goes to the clear-win band, and the occurrence
is recorded.

Draw, all with the seed declared below, fixed before looking at the data:
1. 10 conflicts per cell (dataset x band), simple random sampling. A cell with fewer than 10
   enters whole, and the shortfall is recorded, with no compensation elsewhere.
2. 10 pilot conflicts, outside the sample, 2 per dataset in different bands, with the bands
   rotating across datasets.
3. Blocks: 3 cases of each full cell go to each block, and the tenth case of the full cells is
   spread so that block sizes differ by at most one. The order within a block is drawn, and it is
   the coding order.
4. Per case, the presentation order of the two candidates.

Outputs:
- `--sealed` (a file): every drawn case, with band, `d`, block, position, which tool is candidate A
  and whether the conflict is above SBCR's size limit. It must not reach the coders, since the band
  and the identity of the candidates stay hidden during the coding, so the script refuses to write
  it inside a Git work tree, and only its SHA-256 goes into `draw.json`;
- `--out` (a folder): `coding_sheet.csv` (case, block, position, dataset, chunk id, seed and draw
  date, with no band, no `d` and no candidate identity), `bands.csv` (per dataset and band, the
  conflicts of the band and their share of the frame and of the test partition) and `draw.json`
  (seed, date, script hash and commit, sealed-file hash, thresholds, sizes and occurrences).

    python analysis/rq4/draw_sample.py --root <root of partition 1> --out <dir> --sealed <file outside Git>
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "rq1_rq3"))
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from compare_approaches import evaluated_sets, load_mergegen, split_key  # noqa: E402
from sbcr_scores import OUT_OF_LIMITS, SIM_DRAW, load_sbcr_similarities  # noqa: E402

# Drawn with `secrets.randbelow` before the script ran on the data.
SEED = 1417861201
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
BANDS = ["sbcr", "mergegen", "tie"]
ARM = "mg"
SBCR_SEED = "3022024"
PER_CELL = 10
N_BLOCKS = 3
EXPECTED_FRAME = {"dataset1": 549, "dataset2_Java": 1719, "dataset2_CSharp": 545,
                  "dataset2_JavaScript": 1208, "dataset2_TypeScript": 392}


def build_frame(root, column=SIM_DRAW):
    """Conflicts of the frame, per dataset, with `d`, and the test partition sizes.

    `column` is the similarity that defines `d`: `SIM_DRAW` for the draw, `SIM` for the frame of
    the coding at scale (`build_scale.py`).
    """
    evaluated = evaluated_sets(root)
    sb = load_sbcr_similarities(root)
    sb = sb[(sb.arm == ARM) & (sb.partition == ARM) & (sb.seed == SBCR_SEED)
            & sb.target.isin(DATASETS)]
    sb = sb.assign(sbcr_out_of_limits=sb.status == OUT_OF_LIMITS)
    sb = sb[["target", "chunk_id", column, "sbcr_out_of_limits"]].rename(
        columns={"target": "dataset", column: "sim_sbcr"})
    if sb.duplicated(["dataset", "chunk_id"]).any():
        raise SystemExit(f"SBCR has more than one row per conflict for seed {SBCR_SEED}")

    # by default the column the draw ran with, so that it still draws the same cases
    mg = load_mergegen(root, evaluated, column=column)
    mg = mg[(mg.arm == ARM) & (mg.dataset == mg.model)]
    mg = mg[["dataset", "chunk_id", "mergegen"]].rename(columns={"mergegen": "sim_mergegen"})
    if mg.duplicated(["dataset", "chunk_id"]).any():
        raise SystemExit("MergeGen has more than one candidate per conflict (two model_* folders "
                         "map to the same dataset?)")

    f = sb.merge(mg, on=["dataset", "chunk_id"], how="inner")
    f["d"] = f.sim_sbcr - f.sim_mergegen
    test_size = {ds: len(evaluated[split_key(ds, ARM)]) for ds in DATASETS}
    return f, test_size


def assign_bands(g):
    """Band of each conflict of one dataset, how many fell in two bands, and the thresholds."""
    d = g.d.to_numpy()
    pos, neg, absd = d[d > 0], -d[d < 0], np.abs(d)
    q3_pos = np.quantile(pos, .75) if len(pos) else np.inf
    q3_neg = np.quantile(neg, .75) if len(neg) else np.inf
    q1_abs = np.quantile(absd, .25)
    in_sbcr = (d > 0) & (d >= q3_pos)
    in_mg = (d < 0) & (-d >= q3_neg)
    in_tie = absd <= q1_abs
    overlaps = int(((in_sbcr | in_mg) & in_tie).sum())
    band = np.where(in_sbcr, "sbcr", np.where(in_mg, "mergegen", np.where(in_tie, "tie", "")))
    # None when a dataset has no positive (or no negative) d, so draw.json stays valid JSON
    thresholds = {"q3_positive": float(q3_pos) if np.isfinite(q3_pos) else None,
                  "q3_negative_abs": float(q3_neg) if np.isfinite(q3_neg) else None,
                  "q1_abs": float(q1_abs)}
    return band, overlaps, thresholds


def draw_cells(f, rng):
    sample, leftovers, shortfalls = [], {}, []
    for ds in DATASETS:
        for band in BANDS:
            cell = f[(f.dataset == ds) & (f.band == band)].sort_values("chunk_id")
            n = min(PER_CELL, len(cell))
            if n < PER_CELL:
                shortfalls.append({"dataset": ds, "band": band, "available": len(cell)})
            idx = rng.permutation(len(cell))
            sample.append(cell.iloc[idx[:n]].assign(role="sample"))
            leftovers[(ds, band)] = cell.iloc[idx[n:]]
    return pd.concat(sample, ignore_index=True), leftovers, shortfalls


def draw_pilot(leftovers, rng):
    """2 per dataset, in different bands, with the bands rotating across datasets."""
    start = int(rng.integers(len(BANDS)))
    pilot, deviations = [], []
    for i, ds in enumerate(DATASETS):
        order = [BANDS[(start + 2 * i + k) % len(BANDS)] for k in range(len(BANDS))]
        chosen = 0
        for band in order:
            if chosen == 2:
                break
            rest = leftovers[(ds, band)]
            if len(rest) == 0:
                deviations.append({"dataset": ds, "band": band, "reason": "no leftover in the cell for the pilot"})
                continue
            pilot.append(rest.iloc[[int(rng.integers(len(rest)))]].assign(role="pilot"))
            chosen += 1
    return pd.concat(pilot, ignore_index=True), deviations


def split_into_blocks(sample, rng):
    """Stratified blocks whose sizes differ by at most one, with a drawn order inside each block."""
    sample = sample.copy()
    sample["block"] = 0
    cells = list(sample.groupby(["dataset", "band"], sort=False))
    full = [key for key, g in cells if len(g) == PER_CELL]
    # the tenth case of the full cells goes to the blocks in turn, over a drawn order of the cells
    tenth = {full[i]: 1 + k % N_BLOCKS for k, i in enumerate(rng.permutation(len(full)))}
    load = dict.fromkeys(range(1, N_BLOCKS + 1), 0)
    # full cells first, so that the short ones fill whatever blocks are lightest
    for key, g in sorted(cells, key=lambda kv: len(kv[1]) != PER_CELL):
        blocks = [b for b in load for _ in range(len(g) // N_BLOCKS)]
        if len(g) == PER_CELL:
            blocks.append(tenth[key])
        else:
            for _ in range(len(g) % N_BLOCKS):
                current = {b: load[b] + blocks.count(b) for b in load}
                lightest = [b for b in load if current[b] == min(current.values())]
                blocks.append(lightest[int(rng.integers(len(lightest)))])
        sample.loc[g.index, "block"] = blocks  # g is already in drawn order
        for b in blocks:
            load[b] += 1
    sample["position"] = 0
    for _, g in sample.groupby("block"):
        sample.loc[g.index, "position"] = 1 + rng.permutation(len(g))
    return sample


def inside_git_work_tree(path):
    while not os.path.isdir(path):  # the folder may not exist yet; ask about its nearest ancestor
        path = os.path.dirname(path)
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def git_state():
    """Commit of the checkout that holds this script, and whether tracked files differ from it."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        commit = subprocess.run(["git", "-C", here, "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        changes = subprocess.run(["git", "-C", here, "status", "--porcelain", "--untracked-files=no"],
                                 capture_output=True, text=True, check=True).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None, None
    return commit, bool(changes)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="root of partition 1")
    p.add_argument("--out", required=True, help="directory for the coding sheet, bands.csv and draw.json")
    p.add_argument("--sealed", required=True, help="path of the sealed CSV, outside any Git work tree")
    p.add_argument("--accept-frame-mismatch", action="store_true",
                   help="draw even if the frame sizes differ from EXPECTED_FRAME")
    p.add_argument("--allow-dirty", action="store_true",
                   help="draw even if tracked files differ from the checked-out commit")
    args = p.parse_args()
    root, out, sealed = (os.path.expanduser(x) for x in (args.root, args.out, args.sealed))

    commit, dirty = git_state()
    if dirty and not args.allow_dirty:
        raise SystemExit("tracked files differ from the checked-out commit; commit them first, "
                         "so that draw.json points to the code that made the draw")
    sealed_dir = os.path.dirname(os.path.abspath(sealed))
    if inside_git_work_tree(sealed_dir):
        raise SystemExit(f"{sealed_dir} is inside a Git work tree; put the sealed file elsewhere")
    os.makedirs(sealed_dir, exist_ok=True)

    f, test_size = build_frame(root)
    sizes = {ds: int(n) for ds, n in f.groupby("dataset").size().reindex(DATASETS, fill_value=0).items()}
    mismatches = {ds: {"obtained": n, "expected": EXPECTED_FRAME[ds]}
                  for ds, n in sizes.items() if n != EXPECTED_FRAME[ds]}
    if mismatches:
        msg = f"frame differs from EXPECTED_FRAME: {mismatches}"
        if not args.accept_frame_mismatch:
            raise SystemExit(msg + "\nnothing was written; check --root, or rerun with --accept-frame-mismatch")
        print(f"WARNING: {msg}")

    f["band"] = ""
    overlaps, thresholds = {}, {}
    for ds, g in f.groupby("dataset"):
        band, overlaps[ds], thresholds[ds] = assign_bands(g)
        f.loc[g.index, "band"] = band

    rows = []
    for ds in DATASETS:
        for band in BANDS:
            n = int(((f.dataset == ds) & (f.band == band)).sum())
            rows.append({"dataset": ds, "band": band, "conflicts": n,
                         "share_of_frame": n / sizes[ds] if sizes[ds] else 0.0,
                         "share_of_test": n / test_size[ds] if test_size[ds] else 0.0})
    bands = pd.DataFrame(rows)

    rng = np.random.default_rng(SEED)
    in_band = f[f.band != ""]
    sample, leftovers, shortfalls = draw_cells(in_band, rng)
    pilot, deviations = draw_pilot(leftovers, rng)
    sample = split_into_blocks(sample, rng)
    pilot["block"], pilot["position"] = 0, 1 + rng.permutation(len(pilot))

    cases = pd.concat([sample, pilot], ignore_index=True)
    cases["candidate_a"] = np.where(rng.integers(2, size=len(cases)) == 0, "sbcr", "mergegen")
    cases["candidate_b"] = np.where(cases.candidate_a == "sbcr", "mergegen", "sbcr")
    cases = cases.sort_values(["block", "position"]).reset_index(drop=True)
    cases["case"] = [f"P{p:02d}" if b == 0 else f"B{b}-{p:02d}" for b, p in zip(cases.block, cases.position)]
    today = datetime.date.today().isoformat()

    os.makedirs(out, exist_ok=True)
    bands.to_csv(f"{out}/bands.csv", index=False)
    cases[["case", "role", "block", "position", "dataset", "chunk_id", "band", "d",
           "sim_sbcr", "sim_mergegen", "candidate_a", "candidate_b",
           "sbcr_out_of_limits"]].to_csv(sealed, index=False)
    sheet = cases[["case", "role", "block", "position", "dataset", "chunk_id"]].assign(seed=SEED, draw_date=today)
    sheet.to_csv(f"{out}/coding_sheet.csv", index=False)

    per_block = {int(k): int(v) for k, v in cases[cases.role == "sample"].groupby("block").size().items()}
    record = {
        "seed": SEED, "date": today, "script_sha256": sha256(__file__),
        "git_commit": commit, "git_dirty": dirty,
        "sealed_file": os.path.basename(sealed), "sealed_sha256": sha256(sealed),
        "root": root, "arm": ARM, "sbcr_seed": SBCR_SEED,
        "test_partition": test_size, "frame": sizes, "expected_frame": EXPECTED_FRAME,
        "frame_mismatches": mismatches,
        "sbcr_out_of_limits_in_frame": {ds: int(n) for ds, n in f[f.sbcr_out_of_limits].groupby("dataset")
                                        .size().reindex(DATASETS, fill_value=0).items()},
        "sbcr_out_of_limits_drawn": int(cases.sbcr_out_of_limits.sum()),
        "thresholds": thresholds, "conflicts_in_two_bands": overlaps,
        "short_cells": shortfalls, "pilot_deviations": deviations,
        "cases_per_block": per_block, "pilot": int((cases.role == "pilot").sum()),
    }
    with open(f"{out}/draw.json", "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)

    print(bands.round(3).to_string(index=False))
    print(f"\nsample: {int((cases.role == 'sample').sum())} cases, blocks {per_block}")
    print(f"pilot: {record['pilot']} cases")
    print(f"cases above SBCR's size limit (no SBCR candidate): {record['sbcr_out_of_limits_drawn']}")
    print(f"conflicts in two bands: {overlaps}")
    if shortfalls:
        print(f"short cells: {shortfalls}")
    if deviations:
        print(f"pilot deviations: {deviations}")
    print(f"\nwritten to {out}; sealed file at {sealed} (sha256 {record['sealed_sha256'][:12]}...)")


if __name__ == "__main__":
    main()
