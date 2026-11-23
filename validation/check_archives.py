#!/usr/bin/env python3
"""Checks the downloaded archives and extracts them into one folder.

1. Each zip against `SHA256SUMS`, which lists the SHA-256 of the four zips.
2. Extracts the four zips into `--out`, which must not exist yet. Each zip starts at its own
   folders (`partition-1/`, `rq4/`, ...) and carries `manifests/<archive>.sha256`.
3. Each extracted file against the manifest of its archive (paths relative to `--out`): every
   file listed exists and has its hash, and no file is left unlisted. `sha256sum -c` on each
   manifest, from `--out`, does the same check.

Inputs: the folder of the zips and `SHA256SUMS` (`--zips`). Output: the extracted folder (`--out`)
and the report, on the standard output; exit code 1 if a check fails.

    python validation/check_archives.py --zips <download folder> --out <archives folder>
"""
import argparse
import hashlib
import os
import sys
import zipfile


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--zips", required=True, help="folder with the zips and SHA256SUMS")
    p.add_argument("--out", required=True, help="folder to extract into (must not exist)")
    args = p.parse_args()

    failed = False
    sums = {}
    with open(os.path.join(args.zips, "SHA256SUMS")) as fh:
        for line in fh:
            h, name = line.split(maxsplit=1)
            sums[os.path.basename(name.strip())] = h
    print("Zips against SHA256SUMS")
    for name, want in sorted(sums.items()):
        got = sha256(os.path.join(args.zips, name))
        ok = got == want
        failed |= not ok
        print(f"  {'ok ' if ok else 'BAD'} {name} {got}")

    os.makedirs(args.out)
    print("\nExtraction")
    for name in sorted(sums):
        with zipfile.ZipFile(os.path.join(args.zips, name)) as z:
            names = z.namelist()
            for n in names:
                if n.startswith("/") or ".." in n.split("/"):
                    sys.exit(f"{name}: unsafe path {n}")
            z.extractall(args.out)
            print(f"  {name}: {len(names)} entries")

    print("\nFiles against the manifests")
    listed = set()
    manifests = sorted(f for f in os.listdir(os.path.join(args.out, "manifests")) if f.endswith(".sha256"))
    for m in manifests:
        path = os.path.join(args.out, "manifests", m)
        bad = missing = n = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                h, rel = line.rstrip("\n").split("  ", 1)
                n += 1
                f = os.path.join(args.out, rel)
                if rel in listed:
                    continue
                listed.add(rel)
                if not os.path.exists(f):
                    missing += 1
                    print(f"  MISSING {rel}")
                elif sha256(f) != h:
                    bad += 1
                    print(f"  BAD {rel}")
        failed |= bool(bad or missing)
        print(f"  {os.path.relpath(path, args.out)}: {n} files, {bad} with another hash, {missing} missing")

    unlisted = []
    for d, _, files in os.walk(args.out):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), args.out)
            if rel not in listed and not rel.startswith("manifests/"):
                unlisted.append(rel)
    for rel in unlisted[:20]:
        print(f"  UNLISTED {rel}")
    print(f"  {len(unlisted)} files in no manifest")
    failed |= bool(unlisted)

    print("\narchives " + ("FAILED" if failed else "verified"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
