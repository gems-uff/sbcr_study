#!/usr/bin/env python3
"""Models and SBCR configurations of the random partitions, run on the chronological test.

Compares, on the same conflicts, each tool trained or tuned only on the past (the chronological
split) with the same tool trained or tuned on a partition of the merge-grouped design, whose
training mixes past and future. The references are the three partitions, so that the effect of
chronology can be told apart from the variation of training one more model. The script writes
inside the chronological root and only reads the references' roots. For each reference `<ref>`:

1. MergeGen: links `mergeGen/MODELS/<dataset>_<ref>` to the models of the reference and runs
   `mergegen/jit_inference.py --arm <ref> --test-of mg`, which writes
   `mergeGen/JIT/<dataset>_<ref>__test_mg/model_<dataset>_<ref>/`. The references run one after
   the other, after the GPU queue of the root (`markers/jit.ok`), each with 20 GB free on the GPU.
2. SBCR: evaluates the chronological test of each dataset with the reference's configuration and
   seed 3022024, in `sbcr/eval_<ref>cfg_<dataset>`, a label `sbcr_scores.py` does not read. The
   evaluations share one queue of five slots, counting every SBCR process on the machine, after
   the CPU queue of the root (`markers/sbcr_evaluation.ok`).

Idempotent, with the markers `markers/jit_<ref>.ok` and `markers/sbcr_references.ok`.

    python analysis/chronological/chronological_references.py --root <chronological root> \
        --mergegen-python <python of mergegen-train> \
        --ref p1=<partition 1 root> --ref p2=<partition 2 root> --ref p3=<partition 3 root>
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "pipeline"))
from sbcr_queue import DATASETS, now, sbcr_processes, sbcr_target, spreadsheet  # noqa: E402

SEED = 3022024
GPU_MIB = 20000
SLOTS = 5


def wait_for(path, what):
    while not os.path.exists(path):
        print(f"{now()} waiting for {what} ({path})", flush=True)
        time.sleep(600)


def wait_gpu():
    while True:
        free = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True).stdout.split()[0])
        if free >= GPU_MIB:
            return
        print(f"{now()} waiting for the GPU: {free} MiB free, need {GPU_MIB}", flush=True)
        time.sleep(300)


def test_size(root, dataset):
    a = pd.read_csv(os.path.join(root, "data", f"split_{dataset}_mg.csv"), dtype={"chunk_id": str})
    return int((a.partition == "test").sum())


def mergegen(root, ref, ref_root, python):
    marker = os.path.join(root, "markers", f"jit_{ref}.ok")
    if os.path.exists(marker):
        return
    models = os.path.join(root, "mergeGen", "MODELS")
    for d in DATASETS:
        link = os.path.join(models, f"{d}_{ref}")
        target = os.path.join(ref_root, "mergeGen", "MODELS", f"{d}_mg")
        if not os.path.exists(os.path.join(target, "best_model.pt")):
            sys.exit(f"missing model of {ref}: {target}")
        if not os.path.islink(link):
            os.symlink(target, link)
    for attempt in (1, 2):
        wait_gpu()
        print(f"{now()} MergeGen of {ref} on the chronological test, attempt {attempt}", flush=True)
        with open(os.path.join(root, "mergeGen", "LOGS", f"jit_{ref}.log"), "a") as log:
            subprocess.run([python, os.path.join(REPO, "mergegen", "jit_inference.py"),
                            "--root", root, "--arm", ref, "--test-of", "mg"], stdout=log, stderr=subprocess.STDOUT)
        missing = []
        for d in DATASETS:
            folder = os.path.join(root, "mergeGen", "JIT", f"{d}_{ref}__test_mg", f"model_{d}_{ref}")
            n = test_size(root, d)
            ok = (os.path.exists(os.path.join(folder, "times.csv"))
                  and len(pd.read_csv(os.path.join(folder, "times.csv"))) == n
                  and len(json.load(open(os.path.join(folder, "candidates.json")))) == n)
            if not ok:
                missing.append(d)
                if os.path.exists(os.path.join(folder, "times.csv")):
                    os.remove(os.path.join(folder, "times.csv"))  # jit_inference.py skips a folder with it
        if not missing:
            open(marker, "w").write(now() + "\n")
            print(f"{now()} MergeGen of {ref}: done", flush=True)
            return
        print(f"{now()} incomplete for {ref}: {missing}", flush=True)
    sys.exit(f"MergeGen inference of {ref} incomplete after two attempts")


def sbcr(root, refs):
    marker = os.path.join(root, "markers", "sbcr_references.ok")
    if os.path.exists(marker):
        return
    wait_for(os.path.join(root, "markers", "sbcr_evaluation.ok"), "the CPU queue of the chronological root")
    tasks = []
    for ref, ref_root in refs:
        cfg = pd.read_csv(os.path.join(ref_root, "chosen_configurations.csv"))
        cfg = {r.run.rsplit("_", 1)[0]: r.configuration.replace(" ", "") for r in cfg.itertuples()}
        for d in DATASETS:
            label = f"eval_{ref}cfg_{d}"
            n = len(json.load(open(os.path.join(root, "data", f"{sbcr_target(d)}_testing.json")))["chunk_id"])
            tasks.append({"label": label, "folder": os.path.join(root, "sbcr", label), "n": n,
                          "argv": ["sbcr_evaluate.py", sbcr_target(d), cfg[d], label]})

    def done(t):
        sheet = spreadsheet(t["folder"])
        return sheet is not None and len(sheet) >= t["n"]

    def running(t, procs):
        return any(c == os.path.join(root, "sbcr") and t["label"] in argv for c, argv, _ in procs)

    launched, failures = {}, {}
    while True:
        procs = sbcr_processes()
        pending, busy = [], 0
        for t in tasks:
            proc = launched.get(t["label"])
            if (proc is not None and proc.poll() is None) or running(t, procs):
                busy += 1
                continue
            if proc is not None:
                del launched[t["label"]]
                if not done(t):
                    failures[t["label"]] = failures.get(t["label"], 0) + 1
                    print(f"{now()} FAILED {t['label']} (exit {proc.returncode})", flush=True)
            if done(t):
                continue
            if failures.get(t["label"], 0) >= 2:
                sys.exit(f"{t['label']} failed twice")
            pending.append(t)
        if not pending and busy == 0:
            break
        occupied = len(procs)
        for t in pending:
            if occupied >= SLOTS:
                break
            if os.path.exists(t["folder"]):
                shutil.rmtree(t["folder"])
            log = open(os.path.join(root, "mergeGen", "LOGS", f"{t['label']}.log"), "w")
            launched[t["label"]] = subprocess.Popen([sys.executable] + t["argv"], cwd=os.path.join(root, "sbcr"),
                                                    env=dict(os.environ, SEED=str(SEED)),
                                                    stdout=log, stderr=subprocess.STDOUT)
            print(f"{now()} started {t['label']} ({' '.join(t['argv'][1:])})", flush=True)
            occupied += 1
            time.sleep(3)
        time.sleep(60)
    open(marker, "w").write(now() + "\n")
    print(f"{now()} SBCR with the references' configurations: done", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True, help="chronological root")
    ap.add_argument("--mergegen-python", help="Python of the mergegen-train environment (needed unless --only sbcr)")
    ap.add_argument("--ref", action="append", required=True,
                    help="<label>=<root> of a reference partition, e.g. p1=<root of partition 1>")
    ap.add_argument("--only", choices=("mergegen", "sbcr"), help="run only one of the two parts")
    args = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    refs = [(r.split("=", 1)[0], os.path.abspath(os.path.expanduser(r.split("=", 1)[1]))) for r in args.ref]
    if args.only != "sbcr":
        if not args.mergegen_python:
            ap.error("--mergegen-python is required unless --only sbcr")
        wait_for(os.path.join(root, "markers", "jit.ok"), "the GPU queue of the chronological root")
        for ref, ref_root in refs:
            mergegen(root, ref, ref_root, os.path.expanduser(args.mergegen_python))
    if args.only != "mergegen":
        sbcr(root, refs)


if __name__ == "__main__":
    main()
