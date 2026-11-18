#!/usr/bin/env python3
"""Writes and checks SHA-256 manifests of a folder of data or results.

One line per file, `<sha256>  <path relative to the root>`, as `sha256sum` writes it. A folder
with one file per conflict (the SBCR candidates, tens of thousands of files) can enter as one
aggregate line, `<sha256>  <folder>/ (aggregate of <n> files)`, whose hash is the SHA-256 of the
sorted listing `<sha256>  <name>` of its files. `.xlsx` spreadsheets store a creation date, so a
rerun writes other bytes even with the same data: compare them by content.

`write` lists the files that match `--include` (default: every file), with the folders matching
`--aggregate` as aggregates. `check` recomputes every line of a manifest and reports the paths that
are missing or whose hash differs; it exits with 1 when any does.

    python validation/manifest.py write --root <root> --out <root>.sha256 [--aggregate 'sbcr/*/OUTPUT']
    python validation/manifest.py check --root <root> --manifest <root>.sha256
"""
import argparse
import glob
import hashlib
import os
import re
import sys

AGGREGATE = re.compile(r"^(?P<path>.+)/ \(aggregate of (?P<n>\d+) files\)$")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def aggregate(folder):
    names = sorted(os.listdir(folder))
    listing = "\n".join(f"{sha(os.path.join(folder, n))}  {n}" for n in names)
    return hashlib.sha256(listing.encode()).hexdigest(), len(names)


def write(root, out, include, aggregates):
    folders = sorted({d for pattern in aggregates for d in glob.glob(os.path.join(root, pattern)) if os.path.isdir(d)})
    lines = []
    for pattern in include:
        for f in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            if not os.path.isfile(f) or any(f.startswith(d + os.sep) for d in folders):
                continue
            lines.append(f"{sha(f)}  {os.path.relpath(f, root)}")
    for d in folders:
        h, n = aggregate(d)
        lines.append(f"{h}  {os.path.relpath(d, root)}/ (aggregate of {n} files)")
    seen, unique = set(), []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    with open(out, "w") as f:
        f.write("\n".join(unique) + "\n")
    print(f"{len(unique)} entries written to {out}")


def check(root, manifest):
    problems, n = [], 0
    for line in open(manifest, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            continue
        n += 1
        expected, path = line.split("  ", 1)
        m = AGGREGATE.match(path)
        target = os.path.join(root, m.group("path") if m else path)
        if not os.path.exists(target):
            problems.append(f"missing: {path}")
            continue
        got = aggregate(target)[0] if m else sha(target)
        if got != expected:
            problems.append(f"differs: {path}")
    for p in problems:
        print(p)
    print(f"{n} entries checked, {len(problems)} problems")
    return not problems


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    w = sub.add_parser("write", help="write the manifest of a root")
    w.add_argument("--root", required=True)
    w.add_argument("--out", required=True)
    w.add_argument("--include", action="append", help="glob of the files to list, relative to the root (default **/*)")
    w.add_argument("--aggregate", action="append", default=[], help="glob of the folders listed as one aggregate")
    c = sub.add_parser("check", help="check a root against a manifest")
    c.add_argument("--root", required=True)
    c.add_argument("--manifest", required=True)
    args = p.parse_args()
    root = os.path.expanduser(args.root)
    if args.command == "write":
        write(root, os.path.expanduser(args.out), args.include or ["**/*"], args.aggregate)
    else:
        sys.exit(0 if check(root, os.path.expanduser(args.manifest)) else 1)


if __name__ == "__main__":
    main()
