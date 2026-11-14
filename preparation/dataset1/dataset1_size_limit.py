#!/usr/bin/env python3
"""Dataset1 chunks above SBCR's 20,000-character limit, before and after the base was rebuilt.

`find_base.py` writes empty content for any chunk whose `all_raw_a` or `all_raw_b` has 20,000
characters or more, the limit SBCR applies, and the chunks with empty content were discarded.
The script counts the source chunks with a version of 20,000 characters or more, checks that
none of them is among the chunks used and that every chunk used is in the source with the same
two versions, and gives the longest version among the chunks used.

It also counts the source chunks per resolution strategy (`preparation/combination.py`), on
`solution` as it is and with `before_context` cut from its start and `after_context` from its
end where they match, since `solution` holds the resolution with its context lines.

Inputs: `dataset.json` of the SBES 2022 dataset on FigShare (`--source`) and `dataset1_complete.json` (`--used`).
Output: the counts, on the standard output.

    python -I preparation/dataset1/dataset1_size_limit.py --source <dataset.json> --used <dataset1_complete.json>
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from combination import strategy  # noqa: E402

LIMIT = 20000


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def without_context(r):
    """`solution` with `before_context` cut from its start and `after_context` from its end, where they match."""
    s, before, after = r.solution, r.before_context, r.after_context
    if before and s.startswith(before):
        s = s[len(before):]
    if after and s.endswith(after):
        s = s[:len(s) - len(after)]
    return s


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", required=True)
    p.add_argument("--used", required=True)
    args = p.parse_args()

    source = pd.read_json(args.source)
    used = pd.DataFrame(json.load(open(args.used)))
    source["chunk_id"] = source.chunk_id.astype(str)
    used["chunk_id"] = used.chunk_id.astype(str)
    if source.chunk_id.duplicated().any() or used.chunk_id.duplicated().any():
        raise SystemExit("repeated chunk ids")

    joined = used.merge(source, on="chunk_id", how="left", indicator=True)
    missing = int((joined._merge != "both").sum())
    differ = int(((joined.all_raw_a != joined.v1) | (joined.all_raw_b != joined.v2))[joined._merge == "both"].sum())

    longest = source[["v1", "v2"]].fillna("").apply(lambda c: c.str.len()).max(axis=1)
    above = source[longest >= LIMIT]
    used_longest = used[["all_raw_a", "all_raw_b"]].fillna("").apply(lambda c: c.str.len()).max(axis=1)

    print(f"source: {args.source}\n  sha256 {sha256(args.source)}\n  {len(source):,} chunks")
    print(f"used: {args.used}\n  sha256 {sha256(args.used)}\n  {len(used):,} chunks")
    print(f"used chunks missing from the source: {missing}; with a version that differs from the source: {differ}")
    print(f"source chunks with a version of {LIMIT:,} characters or more: {len(above):,}")
    print(f"  of them among the chunks used: {int(above.chunk_id.isin(used.chunk_id).sum())}")
    print(f"longest version among the chunks used: {int(used_longest.max()):,} characters")

    source = source.fillna("")
    starts = int(sum(bool(r.before_context) and r.solution.startswith(r.before_context) for r in source.itertuples()))
    ends = int(sum(bool(r.after_context) and r.solution.endswith(r.after_context) for r in source.itertuples()))
    print(f"source chunks whose solution starts with before_context: {starts:,}; ends with after_context: {ends:,}")
    for label, resolution in [("solution as it is", lambda r: r.solution), ("context cut", without_context)]:
        counts = Counter(strategy(r.v1, r.v2, resolution(r)) for r in source.itertuples())
        print(f"strategy of the source chunks, {label}: {dict(counts.most_common())}")
    if missing or differ or above.chunk_id.isin(used.chunk_id).any():
        raise SystemExit("the hypothesis does not hold")


if __name__ == "__main__":
    main()
