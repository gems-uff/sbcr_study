#!/usr/bin/env python3
"""Where SBCR's candidates come from, and whether its evaluation function prefers them to the resolution.

Environment `sbcr-analise` (pandas, numpy and pylcs). SBCR reads only V1 and V2, and
`sbcr/sbcr_evaluate.py` rejects a candidate whose text equals a version, but that check compares
the raw strings, and every candidate gets a line break appended (`get_candidate_text`), while the
codes and the similarity set whitespace aside. On partition 1:

1. **Origin of each SBCR candidate**, over the conflicts of the combination subset of the test
   partitions: empty; equal to a version; equal to a version except for the line breaks at its end;
   equal to a version once all whitespace is removed; equal to the base once all whitespace is
   removed; or none of these, checked in this order. It also counts the resolutions that equal a
   version once whitespace is removed.
2. **The evaluation function against the resolution.** SBCR scores a candidate by the mean of its
   similarity to V1 and V2 (`evaluate`). The script scores the developer's resolution with the same
   function, written as SBCR writes a candidate, and compares it with the score of SBCR's candidate,
   for resolutions inside SBCR's search space (its lines are lines of V1 and V2 in the order of each
   version) and outside it. A candidate equal to the resolution once whitespace is removed is
   counted apart (`same`).

The score is recomputed as `evaluate` computes it: the texts are written to files in UTF-8 and read
back as ISO-8859-1, and the similarity is `get_gestalt`. The score of each SBCR candidate is first
checked against the `fitness` column of its result spreadsheet, and a conflict whose score does not
match is left out of item 2 and counted (`check_failed`). `sbcr_evaluate.py` scores the perturbed
candidate of each restart from `str()` of its list of line indexes, not from its text (`f_new =
evaluate(s_new, v1, v2)` in `ils_resolution`), so a restart that finds no neighbor returns the
perturbed candidate with that score; the final candidate keeps the score of its text whenever a
local search moved, which is why the check is expected to pass in almost every conflict.

Bands: the frame and bands of `build_scale.py`, whose totals must be `EXPECTED_BANDS`. With
`--joined` (`joined.csv` of `join_scale.py`), the tables also give the annotator's codes, and the
bands of the join must be those of the frame, conflict by conflict.

Inputs: the root of partition 1 (`--root`) and, optionally, `--joined`.
Outputs, in `--out` (a new folder outside the root and any Git work tree, since `conflicts.csv`
names the band and code of each conflict): `conflicts.csv`, `report.md` and `report.json`.

    python analysis/rq4/sbcr_candidate_origin.py --root <root of partition 1> \
        --joined <join folder>/joined.csv --out <dir>
"""
import argparse
import bisect
import glob
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
import pylcs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from draw_sample import (ARM, BANDS, DATASETS, SBCR_SEED, assign_bands, build_frame,  # noqa: E402
                         git_state, inside_git_work_tree)
from sbcr_scores import SIM, sbcr_data_file  # noqa: E402
TOLERANCE = 1e-9
OUTPUTS = ("conflicts.csv", "report.md", "report.json")
ORIGINS = ["empty", "version_exact", "version_but_final_line_breaks", "version_but_whitespace",
           "base_but_whitespace", "other"]
ORIGIN_NAMES = {"empty": "empty", "version_exact": "a version, exactly",
                "version_but_final_line_breaks": "a version, except for the final line breaks",
                "version_but_whitespace": "a version, once whitespace is removed",
                "base_but_whitespace": "the base, once whitespace is removed", "other": "none of these"}
COMPARISONS = ["resolution_higher", "equal", "candidate_higher"]
BAND_NAMES = {"sbcr": "clear SBCR win", "mergegen": "clear MergeGen win", "tie": "near tie", "": "between the bands"}


# --- the measures ---------------------------------------------------------------------------

def without_whitespace(text):
    """The text with all whitespace removed, as the similarity compares it."""
    return "".join(str(text).split())


def as_sbcr_candidate(text):
    """A sequence of lines written as SBCR writes a candidate: joined by line breaks, one at the end."""
    return "\n".join(str(text).splitlines()) + "\n"


def origin(candidate, v1, v2, base):
    """Category of ORIGINS of an SBCR candidate, and which version it matches ("v1", "v2", "both" or "")."""
    if candidate == "":
        return "empty", ""
    tests = [("version_exact", lambda c, v: c == v),
             ("version_but_final_line_breaks", lambda c, v: c.rstrip("\r\n") == v.rstrip("\r\n")),
             ("version_but_whitespace", lambda c, v: without_whitespace(c) == without_whitespace(v))]
    for name, same in tests:
        hits = [s for s, v in (("v1", v1), ("v2", v2)) if same(candidate, v)]
        if hits:
            return name, hits[0] if len(hits) == 1 else "both"
    if base is not None and without_whitespace(candidate) == without_whitespace(base):
        return "base_but_whitespace", ""
    return "other", ""


def in_search_space(resolution, v1, v2):
    """Whether the lines of `resolution` are lines of V1 and V2 taken in the order of each version.

    The search space of SBCR (`candidate_has_partial_order`): each line of a candidate is a line of
    one version, and the lines taken from a version keep their order in it. The frontier holds,
    after each line of the resolution, the pairs (last line used of V1, last line used of V2) that
    no other pair reachable beats on both.
    """
    where = {"a": defaultdict(list), "b": defaultdict(list)}
    for side, text in (("a", v1), ("b", v2)):
        for i, line in enumerate(str(text).splitlines()):
            where[side][line].append(i)
    frontier = [(-1, -1)]
    for line in str(resolution).splitlines():
        reached = set()
        for i, j in frontier:
            pa, pb = where["a"].get(line, []), where["b"].get(line, [])
            k = bisect.bisect_right(pa, i)
            if k < len(pa):
                reached.add((pa[k], j))
            k = bisect.bisect_right(pb, j)
            if k < len(pb):
                reached.add((i, pb[k]))
        if not reached:
            return False
        frontier = pareto(reached)
    return True


def pareto(pairs):
    """The pairs that no other pair beats or equals on both coordinates."""
    out, best_j = [], None
    for i, j in sorted(pairs):
        if best_j is None or j < best_j:
            out.append((i, j))
            best_j = j
    return out


def as_written(text, encoding="utf-8"):
    """The text as `get_gestalt` reads it back: written in `encoding`, read as ISO-8859-1."""
    return str(text).encode(encoding, errors="replace").decode("iso-8859-1")


def sbcr_gestalt(a, b, encoding="utf-8"):
    """`get_gestalt` of `sbcr/sbcr_evaluate.py` on two texts."""
    a, b = as_written(a, encoding), as_written(b, encoding)
    if a == b:
        return 1
    if len(a) + len(b) == 0:  # get_gestalt divides by zero, prints the error and returns 0
        return 0
    idx = pylcs.lcs_sequence_idx(a, b)
    lcs = "".join(b[i] for i in idx if i != -1)
    return 2 * len(lcs) / (len(a) + len(b))


def sbcr_fitness(candidate, v1, v2, encoding="utf-8"):
    """`evaluate` of `sbcr/sbcr_evaluate.py`: the mean of the similarities to V1 and V2."""
    return (sbcr_gestalt(candidate, v1, encoding) + sbcr_gestalt(candidate, v2, encoding)) / 2


def comparison(fitness_resolution, fitness_candidate):
    if abs(fitness_resolution - fitness_candidate) <= TOLERANCE:
        return "equal"
    return "resolution_higher" if fitness_resolution > fitness_candidate else "candidate_higher"


def measure(candidate, v1, v2, base, resolution, stored_fitness, encoding="utf-8"):
    """Every measure of one conflict SBCR processed, as a dict."""
    kind, version = origin(candidate, v1, v2, base)
    row = {"origin": kind, "origin_version": version,
           "resolution_is_version": without_whitespace(resolution) in (without_whitespace(v1),
                                                                       without_whitespace(v2)),
           "resolution_in_space": in_search_space(resolution, v1, v2),
           "candidate_is_resolution": candidate != "" and without_whitespace(candidate) == without_whitespace(resolution)}
    if candidate == "":
        row.update(fitness_stored=stored_fitness, fitness_candidate=None, fitness_check=False,
                   fitness_resolution=None, comparison="")
        return row
    f_cand = sbcr_fitness(candidate, v1, v2, encoding)
    f_res = sbcr_fitness(as_sbcr_candidate(resolution), v1, v2, encoding)
    check = stored_fitness is not None and abs(f_cand - float(stored_fitness)) <= TOLERANCE
    row.update(fitness_stored=stored_fitness, fitness_candidate=f_cand, fitness_check=check,
               fitness_resolution=f_res, comparison=comparison(f_res, f_cand) if check else "")
    return row


# --- the summaries --------------------------------------------------------------------------

def origin_table(c, by):
    """Conflicts per value of `by` and origin, over the conflicts SBCR processed."""
    done = c[~c.sbcr_out_of_limits]
    rows = []
    for key, g in done.groupby(by, sort=False):
        row = {by: key, "processed": len(g)}
        row.update({o: int((g.origin == o).sum()) for o in ORIGINS})
        row["resolution_is_version"] = int(g.resolution_is_version.sum())
        rows.append(row)
    return pd.DataFrame(rows)


def comparison_table(c, by):
    """Item 2 per value of `by`: the conflicts with a checked score, split by search space and comparison.

    `check_failed` counts the non-empty candidates of the group whose score did not match the stored
    `fitness`, which the other columns leave out. `in_space_same` and `outside_same` count the
    candidates equal to the resolution once whitespace is removed, and the comparison columns count
    the others, so `in_space` is `in_space_same` plus the three `in_space_` comparisons.
    """
    done = c[(~c.sbcr_out_of_limits) & (c.origin != "empty")]
    rows = []
    for key, d in done.groupby(by, sort=False):
        g = d[d.fitness_check.astype(bool)]
        row = {by: key, "checked": len(g), "check_failed": len(d) - len(g),
               "in_space": int(g.resolution_in_space.sum())}
        for prefix, part in (("in_space", g[g.resolution_in_space]), ("outside", g[~g.resolution_in_space])):
            same = part.candidate_is_resolution.astype(bool)
            row[f"{prefix}_same"] = int(same.sum())
            row.update({f"{prefix}_{k}": int((part[~same].comparison == k).sum()) for k in COMPARISONS})
        rows.append(row)
    return pd.DataFrame(rows)


def markdown(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(cols))) + "|"]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(lines)


# --- inputs ---------------------------------------------------------------------------------

def load_conflicts(root, dataset):
    """V1, V2, base and resolution of each conflict, from the file SBCR read (`prepara_sbcr.py`)."""
    with open(sbcr_data_file(root, dataset, ARM), encoding="utf-8") as fh:
        d = json.load(fh)
    return {str(c): {"v1": a, "v2": b, "base": o, "resolution": r}
            for c, a, b, o, r in zip(d["chunk_id"], d["all_raw_a"], d["all_raw_b"], d["all_raw_base"],
                                     d["all_raw_res"])}


def evaluation_folder(root, dataset):
    return os.path.join(root, "sbcr", f"eval_{dataset}_{ARM}_s{SBCR_SEED}")


def load_fitness(root, dataset):
    files = glob.glob(os.path.join(evaluation_folder(root, dataset), "RESULTS", "*.xlsx"))
    if len(files) != 1:
        raise SystemExit(f"{dataset}: expected one result spreadsheet, found {len(files)}")
    r = pd.read_excel(files[0], usecols=["chunk_id", "fitness", "status"], dtype={"chunk_id": str})
    return {k: (None if pd.isna(f) or f == "" else float(f)) for k, f in zip(r.chunk_id, r.fitness)}


def read_candidate(root, dataset, chunk_id):
    # same reading as sbcr_similarity.py and build_packages.py
    with open(os.path.join(evaluation_folder(root, dataset), "OUTPUT", chunk_id), encoding="utf-8",
              errors="replace") as fh:
        return fh.read()


def frame_with_bands(root):
    from build_scale import EXPECTED_BANDS
    f, _ = build_frame(root, column=SIM)
    f = f.copy()
    f["band"] = ""
    for _, g in f.groupby("dataset"):
        band, _, _ = assign_bands(g)
        f.loc[g.index, "band"] = band
    totals = {b: int((f.band == b).sum()) for b in BANDS}
    if totals != EXPECTED_BANDS:
        raise SystemExit(f"the bands are {totals}, not EXPECTED_BANDS, {EXPECTED_BANDS}")
    return f


def load_joined(path, f):
    j = pd.read_csv(path, dtype={"chunk_id": str}, keep_default_na=False)
    codes = [c for c in j.columns if c.startswith("code_")]
    m = f[f.band != ""].merge(j[["dataset", "chunk_id", "band"] + codes], on=["dataset", "chunk_id"],
                              how="outer", suffixes=("", "_joined"), indicator=True, validate="one_to_one")
    if (m._merge != "both").any() or (m.band != m.band_joined).any():
        raise SystemExit("the bands of the frame are not those of joined.csv")
    return j[["dataset", "chunk_id"] + codes], codes


# --- main -----------------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--joined")
    p.add_argument("--out", required=True, help="new folder, outside the root and any Git work tree")
    p.add_argument("--encoding", default="utf-8",
                   help="encoding in which SBCR wrote its files on the machine that ran it")
    args = p.parse_args()
    root, out = os.path.realpath(os.path.expanduser(args.root)), os.path.realpath(os.path.expanduser(args.out))
    if inside_git_work_tree(out):
        raise SystemExit(f"{out} is inside a Git work tree, and the outputs name the band and code of each "
                         "conflict. Nothing was written")
    if os.path.commonpath([root, out]) == root:
        raise SystemExit("--out must be outside the root, which this script does not write to. Nothing was written")
    if any(os.path.exists(os.path.join(out, n)) for n in OUTPUTS):
        raise SystemExit(f"{out} already holds a run. Nothing was written")

    f = frame_with_bands(root)
    rows, started = [], time.time()
    for dataset in DATASETS:
        g = f[f.dataset == dataset]
        content, fitness = load_conflicts(root, dataset), load_fitness(root, dataset)
        missing = set(g.chunk_id) - set(content)
        if missing:
            raise SystemExit(f"{dataset}: {len(missing)} conflicts of the frame are not in the file SBCR read")
        for r in g.itertuples(index=False):
            row = {"dataset": dataset, "chunk_id": r.chunk_id, "band": r.band, "sim_sbcr": r.sim_sbcr,
                   "sbcr_out_of_limits": bool(r.sbcr_out_of_limits)}
            if not r.sbcr_out_of_limits:
                x = content[r.chunk_id]
                row.update(measure(read_candidate(root, dataset, r.chunk_id), x["v1"], x["v2"], x["base"],
                                   x["resolution"], fitness.get(r.chunk_id), args.encoding))
            rows.append(row)
        print(f"{dataset}: {len(g)} conflicts, {time.time() - started:.0f} s", flush=True)
    c = pd.DataFrame(rows)
    for col in ("resolution_is_version", "resolution_in_space", "candidate_is_resolution", "fitness_check"):
        c[col] = c[col].fillna(False).astype(bool)
    c["band_name"] = c.band.map(BAND_NAMES)

    codes = []
    if args.joined:
        j, codes = load_joined(os.path.expanduser(args.joined), f)
        c = c.merge(j, on=["dataset", "chunk_id"], how="left")
        for col in codes:
            c[col] = c[col].fillna("")

    done = c[~c.sbcr_out_of_limits & (c.origin != "empty")]
    failed = done[~done.fitness_check]
    tables = {"origin per dataset": origin_table(c, "dataset"),
              "origin per band": origin_table(c, "band_name"),
              "evaluation function per dataset": comparison_table(c, "dataset"),
              "evaluation function per band": comparison_table(c, "band_name"),
              "evaluation function per origin": comparison_table(c, "origin")}
    if "code_cand" in codes:
        mg = c[c.band == "mergegen"]
        tables["origin per code, clear MergeGen win band"] = origin_table(mg, "code_cand")
        tables["evaluation function per code, clear MergeGen win band"] = comparison_table(mg, "code_cand")

    commit, dirty = git_state()
    report = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": commit,
              "uncommitted_changes": dirty, "root": root, "joined": args.joined, "encoding": args.encoding,
              "conflicts": len(c), "processed": int((~c.sbcr_out_of_limits).sum()),
              "score_check_failed": failed[["dataset", "chunk_id"]].to_dict("records"),
              "tables": {k: v.to_dict("records") for k, v in tables.items()}}
    os.makedirs(out, exist_ok=True)
    c.drop(columns="band_name").to_csv(os.path.join(out, "conflicts.csv"), index=False)
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    md = [f"# Origin of SBCR's candidates and its evaluation function", "",
          f"Run on {report['date']}, commit {commit}{' with uncommitted changes' if dirty else ''}, root `{root}`, "
          f"encoding {args.encoding}. {report['processed']} of {report['conflicts']} conflicts processed by SBCR. "
          f"Score check failed in {len(failed)} of {len(done)} non-empty candidates.", "",
          "Origin columns: " + "; ".join(f"`{k}` {v}" for k, v in ORIGIN_NAMES.items()) + ". "
          "Comparison columns: the score of the resolution under SBCR's evaluation function against that of "
          "SBCR's candidate, for resolutions inside and outside SBCR's search space; `_same` counts the candidates "
          "equal to the resolution once whitespace is removed, and the three comparisons count the others.", ""]
    for name, t in tables.items():
        md += [f"## {name[0].upper()}{name[1:]}", "", markdown(t), ""]
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    print(f"wrote {out}: score check failed in {len(failed)} of {len(done)}")


if __name__ == "__main__":
    main()
