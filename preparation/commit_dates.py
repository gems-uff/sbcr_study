#!/usr/bin/env python3
"""Fetches from GitHub the date of the merge commit of each merge in the five datasets.

The metadata of the datasets carry the repository and the hash of the merge commit, but no
date. The script queries the GitHub GraphQL API for each commit and records whether the
repository still exists, whether the commit is still reachable in it, and its dates.

A merge is the pair (repository, merge commit). A merge present in more than one dataset, as
in Dataset1 and Dataset2_Java, is queried once and lists every dataset it belongs to. With
`--sample N`, the script draws N merges, split equally among the five datasets.

Outcome of each merge (column `status`): `found`, `commit_missing` (the repository exists but
the commit is not reachable), `repo_missing` (the repository no longer exists or is private)
or `error`. `resolved_repo` is the name GitHub answers with, which differs from `repo` when the
repository was renamed or moved. The answers are cached in `<out>/cache.jsonl`, so an
interrupted run resumes. The token is the one of `gh auth token`.

Inputs: `dataset1_metadata.csv` and `dataset2_<language>_metadata.json` in `--data-root`.
Outputs, in `--out`: `commit_dates.csv`, one row per merge, and `commit_dates.json`, the
counts per dataset and status with the hashes of the inputs.

    python preparation/commit_dates.py --data-root <data> --out <dir>/universe
"""

import argparse
import csv
import hashlib
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
API = "https://api.github.com/graphql"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def repo_from_url(url):
    parts = url.rstrip("/").split("github.com/")[-1].split("/")
    return f"{parts[0]}/{parts[1]}"


def load_merges(data_root):
    """Returns {(repo, commit): set of datasets} and the input files read."""
    merges = defaultdict(set)
    inputs = []
    path = data_root / "dataset1_metadata.csv"
    inputs.append(path)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            merges[(repo_from_url(row["url"]), row["sha"])].add("dataset1")
    for name in DATASETS[1:]:
        lang = name.split("_", 1)[1]
        path = data_root / f"dataset2_{lang}_metadata.json"
        inputs.append(path)
        meta = json.load(open(path))
        for repo, commit in zip(meta["repo"], meta["commitHash"]):
            merges[(repo_from_url(repo), commit)].add(name)
    # A repository name is case-insensitive on GitHub: merge keys that differ only in case.
    folded = defaultdict(set)
    for (repo, commit), ds in merges.items():
        folded[(repo.lower(), commit)] |= ds
    return folded, inputs


def draw(merges, n, seed):
    """Returns {(repo, commit): dataset it was drawn for}, n // 5 merges per dataset."""
    per_dataset = n // len(DATASETS)
    rng = random.Random(seed)
    chosen = {}
    for name in DATASETS:
        pool = sorted(k for k, ds in merges.items() if name in ds and k not in chosen)
        for k in rng.sample(pool, per_dataset):
            chosen[k] = name
    return chosen


def token():
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def query_batch(keys, tok):
    fields = []
    for i, (repo, commit) in enumerate(keys):
        owner, name = repo.split("/", 1)
        fields.append(
            f"m{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{"
            f" nameWithOwner"
            f" object(oid: {json.dumps(commit)}) {{ ... on Commit {{ committedDate authoredDate parents {{ totalCount }} }} }}"
            f" }}"
        )
    body = json.dumps({"query": "query { " + " ".join(fields) + " rateLimit { cost remaining resetAt } }"}).encode()
    req = urllib.request.Request(API, data=body, headers={"Authorization": f"bearer {tok}", "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) or (e.code == 403 and attempt < 4):
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(30 * (attempt + 1))
    raise RuntimeError("GitHub API did not answer after 5 attempts")


def parse(keys, answer):
    data = answer.get("data") or {}
    errors = defaultdict(list)
    for err in answer.get("errors", []):
        path = err.get("path") or [None]
        errors[path[0]].append(err)
    rows = []
    for i, (repo, commit) in enumerate(keys):
        alias = f"m{i}"
        node = data.get(alias)
        row = {"repo": repo, "commit": commit, "resolved_repo": "", "committed_date": "", "authored_date": "",
               "parents": "", "status": "", "error": ""}
        if node is None:
            errs = errors.get(alias, [])
            if errs and all(e.get("type") == "NOT_FOUND" for e in errs):
                row["status"] = "repo_missing"
            else:
                row["status"] = "error"
                row["error"] = "; ".join(e.get("message", "") for e in errs) or "no data"
        else:
            row["resolved_repo"] = node["nameWithOwner"]
            obj = node.get("object")
            if obj is None:
                row["status"] = "commit_missing"
            elif "committedDate" not in obj:
                row["status"] = "error"
                row["error"] = "object is not a commit"
            else:
                row.update(status="found", committed_date=obj["committedDate"], authored_date=obj["authoredDate"],
                           parents=obj["parents"]["totalCount"])
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sample", type=int, help="number of merges to draw, split equally among the five datasets")
    ap.add_argument("--seed", type=int, help="seed of the draw, required with --sample")
    ap.add_argument("--batch", type=int, default=50)
    args = ap.parse_args()

    out = args.out.expanduser().resolve()
    if args.sample and args.seed is None:
        sys.exit("--sample needs --seed")
    out.mkdir(parents=True, exist_ok=True)

    merges, inputs = load_merges(args.data_root.expanduser())
    drawn_for = draw(merges, args.sample, args.seed) if args.sample else {}
    keys = list(drawn_for) if args.sample else sorted(merges)

    cache_path = out / "cache.jsonl"
    cache = {}
    if cache_path.exists():
        for line in open(cache_path):
            r = json.loads(line)
            cache[(r["repo"], r["commit"])] = r
    todo = [k for k in keys if k not in cache or cache[k]["status"] == "error"]
    print(f"{len(keys)} merges, {len(keys) - len(todo)} already cached, {len(todo)} to query", flush=True)

    tok = token() if todo else None
    with open(cache_path, "a") as cf:
        for start in range(0, len(todo), args.batch):
            batch = todo[start:start + args.batch]
            answer = query_batch(batch, tok)
            for row in parse(batch, answer):
                cache[(row["repo"], row["commit"])] = row
                cf.write(json.dumps(row) + "\n")
            cf.flush()
            rl = (answer.get("data") or {}).get("rateLimit") or {}
            print(f"{min(start + args.batch, len(todo))}/{len(todo)} queried, rate limit remaining {rl.get('remaining')}",
                  flush=True)
            if rl.get("remaining") is not None and rl["remaining"] < 50:
                time.sleep(max(0, time.mktime(time.strptime(rl["resetAt"], "%Y-%m-%dT%H:%M:%SZ")) - time.mktime(time.gmtime())) + 60)

    columns = ["repo", "commit", "datasets", "drawn_for", "status", "resolved_repo", "committed_date", "authored_date", "parents", "error"]
    csv_path = out / "commit_dates.csv"
    counts = defaultdict(Counter)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for k in keys:
            row = dict(cache[k], datasets=";".join(d for d in DATASETS if d in merges[k]), drawn_for=drawn_for.get(k, ""))
            w.writerow({c: row[c] for c in columns})
            # In a sample, a merge counts for the dataset it was drawn for; in the universe, for every dataset it is in.
            for d in ([drawn_for[k]] if args.sample else merges[k]):
                counts[d][row["status"]] += 1
            counts["all"][row["status"]] += 1

    summary = {
        "sample": args.sample, "seed": args.seed, "merges_in_universe": len(merges), "merges_queried": len(keys),
        "counts": {d: dict(counts[d]) for d in DATASETS + ["all"] if d in counts},
        "inputs": {str(p): sha256(p) for p in inputs},
        "commit_dates.csv": sha256(csv_path),
    }
    (out / "commit_dates.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["counts"], indent=2))
    print(f"wrote {csv_path} and {out / 'commit_dates.json'}")


if __name__ == "__main__":
    main()
