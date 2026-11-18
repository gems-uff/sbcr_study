#!/usr/bin/env python3
"""Runs the SBCR evaluations of the first rerun that are still missing, and only those.

`sbcr_evaluate.py` writes partial results every five conflicts but does not resume, so an
interruption leaves incomplete spreadsheets that look finished. The script counts the rows of
each result, takes as done only those that reached the size of the test partition, deletes
the partial ones and queues the rest, five seeds and three arms per target.

Inputs, under `--root`: `selected_configurations.csv` (`select_configuration.py`) and the
partitions of `prepare_sbcr.py`. Outputs: `<root>/sbcr/eval_<target>_<arm>_s<seed>/` and their
logs in `<root>/mergeGen/LOGS/`.

    python sbcr/resume_evaluations.py --root <root> [--slots 5] [--list-only]
"""
import argparse
import os
import shutil
import subprocess
import time

import pandas as pd

TARGETS = {  # name -> (base dataset, conflicts in the test, uses the configuration of)
    "dataset1": ("dataset1", 549, "dataset1"),
    "dataset2_Java": ("dataset2_Java", 1717, "dataset2_Java"),
    "dataset2_CSharp": ("dataset2_CSharp", 546, "dataset2_CSharp"),
    "dataset2_JavaScript": ("dataset2_JavaScript", 1207, "dataset2_JavaScript"),
    "dataset2_TypeScript": ("dataset2_TypeScript", 392, "dataset2_TypeScript"),
    "rq3_ds1": ("dataset1", 549, "dataset2_Java"),      # RQ3 swaps the configurations
    "rq3_java": ("dataset2_Java", 1717, "dataset1"),
}
SEEDS = ["3022024", "20260904", "7412", "98765", "31337"]
ARMS = ["random", "mg", "pd"]
# seconds per conflict, to order the queue and estimate its length
COST = {"dataset1": 4.79, "dataset2_Java": 4.03, "dataset2_CSharp": 2.57,
        "dataset2_JavaScript": 14.81, "dataset2_TypeScript": 8.68,
        "rq3_ds1": 4.03, "rq3_java": 4.79}


def status(root, label, expected):
    """'done', 'partial' or 'missing'."""
    folder = os.path.join(root, "sbcr", f"eval_{label}")
    if not os.path.isdir(folder):
        return "missing", folder
    files = [os.path.join(dp, f) for dp, _, fs in os.walk(folder) for f in fs if f.endswith(".xlsx")]
    if not files:
        return "partial", folder
    try:
        n = max(len(pd.read_excel(a)) for a in files)
    except Exception:
        return "partial", folder
    return ("done" if n >= expected else "partial"), folder


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--slots", type=int, default=5, help="evaluations running at the same time")
    p.add_argument("--list-only", action="store_true")
    args = p.parse_args()
    root = os.path.expanduser(args.root)

    cfgs = pd.read_csv(os.path.join(root, "selected_configurations.csv"))
    cfg = {(r.run.rsplit("_", 1)[0], r.run.rsplit("_", 1)[1]): r.configuration.replace(" ", "")
           for r in cfgs.itertuples()}

    pending, done = [], 0
    for arm in ARMS:
        for target, (base, n, source) in TARGETS.items():
            for seed in SEEDS:
                label = f"{target}_{arm}_s{seed}"
                st, folder = status(root, label, n)
                if st == "done":
                    done += 1
                    continue
                if st == "partial" and not args.list_only:
                    shutil.rmtree(folder, ignore_errors=True)
                dataset = f"dataset1_{arm}" if base == "dataset1" else f"{base}_{arm}_combination"
                pending.append({"label": label, "dataset": dataset, "config": cfg[(source, arm)],
                                "cost": n * COST[target], "status": st})

    pending.sort(key=lambda x: -x["cost"])
    hours = sum(x["cost"] for x in pending) / 3600
    print(f"done: {done}   pending: {len(pending)}")
    print(f"estimated work: {hours:.1f} CPU hours -> ~{hours/args.slots:.1f} h with {args.slots} slots")
    for x in pending[:8]:
        print(f"  {x['label']:40s} {x['status']:8s} {x['cost']/3600:.2f} h")
    if len(pending) > 8:
        print(f"  ... and {len(pending)-8} more")
    if args.list_only or not pending:
        return

    sbcr = os.path.join(root, "sbcr")
    logs = os.path.join(root, "mergeGen", "LOGS")
    running = []
    for x in pending:
        while len(running) >= args.slots:
            running = [p for p in running if p.poll() is None]
            if len(running) >= args.slots:
                time.sleep(30)
        env = dict(os.environ, SEED=x["label"].rsplit("_s", 1)[1])
        log = open(os.path.join(logs, f"eval_{x['label']}.log"), "w")
        print(f"{time.strftime('%H:%M:%S')} starts {x['label']} ({x['config']})", flush=True)
        running.append(subprocess.Popen(
            ["python", "sbcr_evaluate.py", x["dataset"], x["config"], f"eval_{x['label']}"],
            cwd=sbcr, env=env, stdout=log, stderr=subprocess.STDOUT))
    for p_ in running:
        p_.wait()
    print(f"{time.strftime('%H:%M:%S')} queue finished", flush=True)


if __name__ == "__main__":
    main()
