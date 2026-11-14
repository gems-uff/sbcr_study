#!/usr/bin/env python3
"""Step-by-step trace from the 13,573 chunks of Dataset1's public source to the 6,269 it uses.

The source is `dataset.json` of the SBES 2022 dataset on FigShare
(https://doi.org/10.6084/m9.figshare.26831818, version 4). The same item holds
`dataset_processed_base.json`, with the 6,269 chunks of Dataset1. Two scripts carry the rules
that explain the difference: `find_base.py`, which writes an empty base when a version has
20,000 characters or more, when the region of the conflict cannot be located at a single
position and, by construction, when the region it locates is empty; and `get_clean_solution`
of `transform_sbes2022_dataset.py`, which returns `None` when the context of the resolution
does not match that of the chunk. The script runs both rules on every source chunk and
assigns each chunk to the first step that removes it:

1. a version of 20,000 characters or more;
2. the region of the conflict not located at a single position of the base file;
3. the region located, but empty;
4. the context of the resolution does not match that of the chunk.

It then checks that the chunks left are exactly those of `--package`, with the base that
`find_base.py` rebuilds and the other columns equal to the source. It also gives the counts
in the other order (step 4 first), and splits step 2 by whether the context before the chunk
has fewer than two lines, the case in which `find_base.py` makes no attempt.

Inputs: `dataset.json` (`--source`) and `dataset_processed_base.json` (`--package`).
Outputs, in `--out`: `dataset1_trace.txt` (the counts) and `dataset1_trace.csv` (the step of each chunk).

    python -I preparation/dataset1/dataset1_trace.py --source <dataset.json> \
        --package <dataset_processed_base.json> --out <dir>
"""
import argparse
import hashlib
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_base  # noqa: E402
import transform_sbes2022_dataset  # noqa: E402

LIMIT = 20000
STEPS = ["version_20000_chars_or_more", "region_not_located", "region_empty", "resolution_context_mismatch"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", required=True)
    p.add_argument("--package", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    paths = {k: os.path.expanduser(getattr(args, k)) for k in ["source", "package"]}
    paths["find_base"] = find_base.__file__
    paths["transform"] = transform_sbes2022_dataset.__file__
    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)

    locate = find_base.locate_conflict_region
    clean = transform_sbes2022_dataset.get_clean_solution

    source = pd.read_json(paths["source"])
    package = pd.read_json(paths["package"])
    if source.chunk_id.duplicated().any() or package.chunk_id.duplicated().any():
        raise SystemExit("repeated chunk ids")

    rows = []
    for r in source.itertuples():
        above = len(r.v1) >= LIMIT or len(r.v2) >= LIMIT
        region = None if above else locate(r.base, r.before_context, r.after_context)
        content = region[2] if region else ""
        mismatch = clean(r.solution, r.before_context, r.after_context) is None
        if above:
            step = STEPS[0]
        elif not region:
            step = STEPS[1]
        elif content == "":
            step = STEPS[2]
        elif mismatch:
            step = STEPS[3]
        else:
            step = "kept"
        rows.append(dict(chunk_id=r.chunk_id, step=step, rebuilt_base_empty=(content == ""),
                         context_mismatch=mismatch, before_context_lines=len(r.before_context.splitlines()),
                         rebuilt_base=content))
    trace = pd.DataFrame(rows)

    kept = trace[trace.step == "kept"]
    joined = package.merge(source, on="chunk_id", how="left", suffixes=("", "_source"), indicator=True)
    joined = joined.merge(trace[["chunk_id", "rebuilt_base"]], on="chunk_id", how="left")
    same_set = set(kept.chunk_id) == set(package.chunk_id)
    differ = {c: int((joined[c] != joined[c + "_source"]).sum())
              for c in ["v1", "v2", "solution", "before_context", "after_context"]}
    differ["base_complete"] = int((joined.base_complete != joined.base_source).sum())
    differ["base"] = int((joined.base != joined.rebuilt_base).sum())
    package_mismatch = int(sum(clean(r.solution, r.before_context, r.after_context) is None
                               for r in package.itertuples()))

    lines = [f"source: {paths['source']}\n  sha256 {sha256(paths['source'])}\n  {len(source):,} chunks",
             f"package: {paths['package']}\n  sha256 {sha256(paths['package'])}\n  {len(package):,} chunks",
             f"find_base.py: {paths['find_base']}\n  sha256 {sha256(paths['find_base'])}",
             f"transform: {paths['transform']}\n  sha256 {sha256(paths['transform'])}",
             "", "removals, each chunk at the first step that removes it:"]
    left = len(source)
    for step in STEPS:
        n = int((trace.step == step).sum())
        left -= n
        lines.append(f"  {step}: {n:,} (left {left:,})")
    lines.append(f"  kept: {len(kept):,}")
    short = trace[(trace.step == STEPS[1]) & (trace.before_context_lines < 2)]
    lines.append(f"of {STEPS[1]}: before_context with fewer than two lines {len(short):,}, "
                 f"with two or more {int((trace.step == STEPS[1]).sum()) - len(short):,}")

    lines.append("")
    lines.append("other order, step 4 first:")
    first = trace.context_mismatch
    lines.append(f"  resolution_context_mismatch: {int(first.sum()):,} (left {len(trace) - int(first.sum()):,})")
    rest = trace[~first]
    left = len(rest)
    for step in STEPS[:3]:
        n = int((rest.step == step).sum())
        left -= n
        lines.append(f"  {step}: {n:,} (left {left:,})")
    lines.append(f"chunks with an empty rebuilt base (steps 1 to 3): {int(trace.rebuilt_base_empty.sum()):,}; "
                 f"with a context mismatch: {int(trace.context_mismatch.sum()):,}; "
                 f"both: {int((trace.rebuilt_base_empty & trace.context_mismatch).sum()):,}")

    lines.append("")
    lines.append(f"chunks kept equal to the package chunks: {same_set}")
    lines.append(f"package chunks missing from the source: {int((joined._merge != 'both').sum())}")
    lines.append(f"package chunks whose column differs from the source (base: from the rebuilt base): {differ}")
    lines.append(f"package chunks for which get_clean_solution returns None: {package_mismatch}")
    report = "\n".join(lines)
    print(report)
    open(os.path.join(out, "dataset1_trace.txt"), "w").write(report + "\n")
    trace.drop(columns="rebuilt_base").to_csv(os.path.join(out, "dataset1_trace.csv"), index=False)

    if not same_set or any(differ.values()) or package_mismatch or (joined._merge != "both").any():
        raise SystemExit("the trace does not reproduce the package")


if __name__ == "__main__":
    main()
