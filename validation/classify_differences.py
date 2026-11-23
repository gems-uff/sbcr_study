#!/usr/bin/env python3
"""Classifies the text outputs that `run_analysis.py` found different from the archived ones.

Reads `comparison.tsv` and, for each text file marked `differs`, compares the two files again
after each normalization below, in order, and gives the first that makes them equal:

- `spacing`: runs of spaces collapsed. The translation of the archives replaced Portuguese column
  names with English ones of another length, which moves the alignment of printed tables;
- `elapsed times`: also numbers followed by a unit of time (`0.3 min`, `12 s`) and timestamps;
- `paths`: also the absolute paths of the run (`/w/...`, the folder of the archives);
- `hashes and commits`: also hexadecimal strings of 40 or 64 characters;
- `lines in another order`: the same lines after these normalizations, in another order (the
  arm `random` sorts after `mg` and `pd`, and R interleaves its messages with its output).

A JSON output is `provenance` when it differs only in the paths of the run, the commit, the date
of the run and the hashes it records of the script, its inputs and its outputs, which the
archives give for the files before their translation. A CSV output is `date of the run` when it
differs only in a column that holds that date (`draw_date` of the coding sheets).

A file that stays different is `content` and is read by a person. A CSV or JSON file is compared
again with the comparison of `run_analysis.py`, which matches rows in another order.

Inputs: the folder of the archives (`--archives`), the work copy (`--work`) and the logs of
`run_analysis.py` (`--logs`). Output: `<logs>/differences.tsv` (step, path, class, the first
differing lines) and a count per class on the standard output.

    python validation/classify_differences.py --archives /data --work /work-copy --logs /out/logs
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_analysis import archived_path, compare, flatten, steps  # noqa: E402

STEPS = [
    ("spacing", lambda s: re.sub(r"[ \t]+", " ", s).strip()),
    ("elapsed times", lambda s: re.sub(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?([+-]\d\d:\d\d|Z)?|\b\d+(\.\d+)?\s?(min|s|sec|seconds|minutes|h)\b",
        "<time>", s)),
    # the archives name the files of the run relative to the folder of the archives
    ("paths", lambda s: re.sub(r"(/package|/submitted|/backbone)(/[^\s'\",)]*)?", "<path>",
                               re.sub(r"(?<![\w.])/(w|archives)/", "",
                                      re.sub(r"\S*/envs/([\w-]+)/lib/", r"<envs>/\1/lib/", s)))),
    ("hashes and commits", lambda s: re.sub(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b", "<hash>", s)),
]


def lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [l.rstrip() for l in fh.read().splitlines() if l.strip()]


def classify(new, old):
    a, b = lines(new), lines(old)
    for name, f in STEPS:
        a, b = [f(l) for l in a], [f(l) for l in b]
        if a == b:
            return name, ""
    if sorted(a) == sorted(b):
        return "lines in another order", ""
    first = next(((x, y) for x, y in zip(b, a) if x != y), (b[len(a):][:1] or [""], a[len(b):][:1] or [""]))
    return "content", f"archived: {first[0]!s:.200} | new: {first[1]!s:.200}"


PROVENANCE = re.compile(r"^\.(commit|git_commit|root|data_root|tokenizer|references|inputs|dates|outputs|decoded|"
                        r"decoded_changed|joined|date|generated|script_sha256|coding_sheet_sha256)\b")
RUN_DATE_COLUMNS = {"draw_date"}


def run_date_only(new, old):
    """Whether two CSV files differ only in a column that holds the date of the run."""
    with open(new, encoding="utf-8", newline="") as f1, open(old, encoding="utf-8", newline="") as f2:
        a, b = list(csv.reader(f1)), list(csv.reader(f2))
    if len(a) != len(b) or a[:1] != b[:1]:
        return False
    keep = [i for i, c in enumerate(a[0]) if c not in RUN_DATE_COLUMNS]
    return len(keep) < len(a[0]) and all([r[i] for i in keep] == [q[i] for i in keep] for r, q in zip(a[1:], b[1:]))


def provenance_only(new, old):
    """Whether two JSON outputs differ only in the paths of the run, the commit, the hashes of
    inputs and outputs (the archives record those of the files before translation) and the keys
    of the inputs given by path, all else equal."""
    def norm(d):
        return {re.sub(r"(\.\./)?/(w|archives)/", "", k): (re.sub(r"^/(w|archives)/", "", v) if isinstance(v, str) else v)
                for k, v in d.items()}
    a, b = norm(dict(flatten(json.load(open(new))))), norm(dict(flatten(json.load(open(old)))))
    for k in set(a) | set(b):
        x, y = a.get(k), b.get(k)
        if x == y or (isinstance(x, float) and isinstance(y, float) and abs(x - y) <= 1e-9 * max(abs(x), abs(y))):
            continue
        if not PROVENANCE.match(k):
            return False
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--archives", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--logs", required=True)
    args = p.parse_args()

    moved = {s["name"]: s["moved"] for s in steps("/w", "/submitted")}
    out, counts = [], Counter()
    with open(os.path.join(args.logs, "comparison.tsv"), encoding="utf-8") as fh:
        rows = list(csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))
    for step, rel, kind, *rest in rows:
        if kind != "differs":
            continue
        archived = archived_path(rel, moved.get(step, {}))
        old, new = os.path.join(args.archives, archived), os.path.join(args.work, rel)
        if not os.path.exists(old):
            continue
        if rel.endswith(".json") and provenance_only(new, old):
            cls, detail = "provenance", ""
        elif rel.endswith(".csv") and run_date_only(new, old):
            cls, detail = "date of the run", ""
        elif rel.endswith((".csv", ".json")):
            detail, ok = compare(new, old)
            cls, detail = (detail, "") if ok else ("content", detail)
        else:
            cls, detail = classify(new, old)
        counts[cls] += 1
        out.append((step, rel, cls, detail))
    with open(os.path.join(args.logs, "differences.tsv"), "w", encoding="utf-8") as fh:
        for row in out:
            fh.write("\t".join(row) + "\n")
    for cls, n in counts.most_common():
        print(f"{cls}: {n}")


if __name__ == "__main__":
    main()
