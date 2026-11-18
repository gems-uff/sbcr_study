#!/usr/bin/env python3
"""CPU queue of the merge-grouped partitions: SBCR tuning, selection and evaluation.

Per root, only the `mg` arm: five tunings with the grid on 100 training conflicts; then the
selection rule of `sbcr/select_configuration.py`; then seven evaluations per seed, the five
datasets and the two crossed ones of RQ3, in which Dataset1 and Dataset2_Java swap
configurations. The default seed is 3022024; `--seeds` takes several. If the root has the `pd`
slices (`prepare_partition.sh` with `PD_FROM`), it adds the seven evaluations of the common set,
with the configuration of `mg` on the test partition of `pd` and seed 3022024
(`eval_common_<target>_mg`).

One global queue of five slots for all roots together, counting every SBCR process on the
machine: SBCR's search is bounded by wall-clock time, so more simultaneous processes would let
each configuration complete fewer iterations, changing the similarity and not only the
duration. For the same reason, the queue launches nothing while the 1-minute load average is
above `--max-load`, and when the load stays above it for `--overload-minutes` while tasks run, it
kills them, with their process groups, and redoes them once the load is back under the limit.
Every round writes the load to `logs/sbcr_load.csv`.

Idempotent: neither the tuning nor the evaluation resumes, so a task counts as done by its
content (the tuning with 8,000 `ok` rows, the evaluation with one row per test conflict), and a
task neither done nor running is deleted and redone. Running processes are recognized by their
working directory, so a relaunched queue adopts them. Each seed of a root closes with a marker,
`markers/sbcr_evaluation.ok` for seed 3022024 and `markers/sbcr_evaluation_s<seed>.ok` for the
others. Starts and ends go to `logs/sbcr_queue.csv`.

    ROOTS="<root 2> <root 3>" python pipeline/sbcr_queue.py
    python pipeline/sbcr_queue.py --roots <root 1> --seeds 20260904 7412 98765 31337
"""
import argparse
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
GRID = 5 * 4 * 4
NUM_CHUNKS = 100
DEFAULT_SEED = 3022024
# target -> (evaluated dataset, dataset whose configuration is used)
TARGETS = {d: (d, d) for d in DATASETS}
TARGETS.update({"rq3_ds1": ("dataset1", "dataset2_Java"), "rq3_java": ("dataset2_Java", "dataset1")})
# To order the queue, longest first: tuning hours and seconds per evaluated conflict.
TUNING_HOURS = {"dataset1": 10.8, "dataset2_JavaScript": 9.9, "dataset2_CSharp": 9.1,
                "dataset2_Java": 8.4, "dataset2_TypeScript": 7.9}
S_PER_CONFLICT = {"dataset1": 4.79, "dataset2_Java": 4.03, "dataset2_CSharp": 2.57,
                  "dataset2_JavaScript": 14.81, "dataset2_TypeScript": 8.68,
                  "rq3_ds1": 4.03, "rq3_java": 4.79}
SCRIPTS = ("sbcr_tuning.py", "sbcr_evaluate.py")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sbcr_processes():
    """(cwd, argv, pid) of each SBCR process on the machine."""
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
            argv = [a.decode(errors="replace") for a in argv if a]
            if len(argv) < 2 or os.path.basename(argv[1]) not in SCRIPTS:
                continue
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except (OSError, IndexError):
            continue
        found.append((cwd, argv, int(pid)))
    return found


def sbcr_target(base, arm="mg"):
    return f"dataset1_{arm}" if base == "dataset1" else f"{base}_{arm}_combination"


def spreadsheet(folder):
    files = glob.glob(os.path.join(folder, "RESULTS", "*.xlsx"))
    if not files:
        return None
    try:
        return max((pd.read_excel(a) for a in files), key=len)
    except Exception:
        return None


DONE = set()  # a done task does not regress; avoids rereading the spreadsheet on every round


def done(task):
    key = (task["root"], task["label"])
    if key in DONE:
        return True
    ok = _done(task)
    if ok:
        DONE.add(key)
    return ok


def _done(task):
    d = spreadsheet(task["folder"])
    if d is None:
        return False
    if task["kind"] == "tuning":
        return int((d.status == "ok").sum()) >= NUM_CHUNKS * GRID
    return len(d) >= task["n"]


def tunings_of(root):
    sbcr = os.path.join(root, "sbcr")
    tunings = []
    for ds in DATASETS:
        label = f"tuning_{ds}_mg"
        tunings.append({"root": root, "kind": "tuning", "label": label, "folder": os.path.join(sbcr, label),
                        "argv": ["sbcr_tuning.py", sbcr_target(ds), label],
                        "env": {"NUM_CHUNKS": str(NUM_CHUNKS)}, "cost": TUNING_HOURS[ds] * 3600})
    return tunings


def evaluations_of(root, seed):
    sbcr = os.path.join(root, "sbcr")
    cfg = pd.read_csv(os.path.join(root, "selected_configurations.csv"))
    cfg = {r.run.rsplit("_", 1)[0]: r.configuration.replace(" ", "") for r in cfg.itertuples()}
    tasks = []
    for target, (base, source) in TARGETS.items():
        label = f"eval_{target}_mg_s{seed}"
        n = len(json.load(open(os.path.join(root, "data", f"{sbcr_target(base)}_testing.json")))["chunk_id"])
        tasks.append({"root": root, "kind": "evaluation", "label": label, "folder": os.path.join(sbcr, label),
                      "argv": ["sbcr_evaluate.py", sbcr_target(base), cfg[source], label], "n": n,
                      "env": {"SEED": str(seed)}, "cost": n * S_PER_CONFLICT[target]})
        if seed == DEFAULT_SEED and os.path.exists(
                os.path.join(root, "data", f"{sbcr_target(base, 'pd')}_testing.json")):
            label = f"eval_common_{target}_mg"
            n = len(json.load(open(os.path.join(root, "data", f"{sbcr_target(base, 'pd')}_testing.json")))["chunk_id"])
            tasks.append({"root": root, "kind": "evaluation", "label": label, "folder": os.path.join(sbcr, label),
                          "argv": ["sbcr_evaluate.py", sbcr_target(base, "pd"), cfg[source], label], "n": n,
                          "env": {"SEED": str(seed)}, "cost": n * S_PER_CONFLICT[target]})
    return tasks


def evaluation_marker(root, seed):
    name = "sbcr_evaluation.ok" if seed == DEFAULT_SEED else f"sbcr_evaluation_s{seed}.ok"
    return os.path.join(root, "markers", name)


def task_pids(task, procs):
    cwd = os.path.join(task["root"], "sbcr")
    return [pid for c, argv, pid in procs
            if c == cwd and argv[1:] and os.path.basename(argv[1]) == task["argv"][0] and task["label"] in argv]


def kill_task_process(pid):
    """Kills a task's process with its process group, when it leads one.

    The queue launches each task in a session of its own, so the task leads its group, which
    also holds the shell and SBCR. A task adopted from another process group is killed alone.
    """
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def running(task, procs):
    return bool(task_pids(task, procs))


def log_load(root, load, n_sbcr):
    path = os.path.join(root, "logs", "sbcr_load.csv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("when,load1,load5,load15,sbcr_processes\n")
        f.write(f"{now()},{load[0]:.2f},{load[1]:.2f},{load[2]:.2f},{n_sbcr}\n")


def free_disk_gb(path):
    return shutil.disk_usage(path).free / 1024 ** 3


def log_event(root, line):
    path = os.path.join(root, "logs", "sbcr_queue.csv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("label,event,when,detail\n")
        f.write(line + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--roots", default=os.environ.get("ROOTS", ""), help="roots, space-separated (or ROOTS)")
    p.add_argument("--slots", type=int, default=5)
    p.add_argument("--seeds", type=int, nargs="+", default=[DEFAULT_SEED])
    p.add_argument("--failures", type=int, default=2, help="gives up on a task after this many failures")
    p.add_argument("--list-only", action="store_true", help="shows the state and exits, launching nothing")
    p.add_argument("--min-disk", type=float, default=50, help="free GB required before launching")
    p.add_argument("--max-load", type=float, default=24,
                   help="1-minute load average above which nothing is launched; 0 turns the guard off")
    p.add_argument("--overload-minutes", type=float, default=5,
                   help="minutes above --max-load, with tasks running, after which they are killed and redone")
    args = p.parse_args()
    roots = [os.path.abspath(os.path.expanduser(r)) for r in args.roots.split()]
    if not roots:
        p.error("set ROOTS or --roots")
    for r in roots:
        if not os.path.exists(os.path.join(r, "markers", "sbcr.ok")):
            p.error(f"{r} has no finished preparation")

    launched, failures = {}, {}
    overloaded_since = None
    while True:
        procs = sbcr_processes()
        pending, active, in_progress, abandoned = [], [], 0, 0
        for root in roots:
            seeds = [s for s in args.seeds if not os.path.exists(evaluation_marker(root, s))]
            if not seeds:
                continue
            groups = [(None, tunings_of(root))]
            tuning_ok = all(not running(t, procs) and done(t) for t in groups[0][1])
            choices = os.path.join(root, "selected_configurations.csv")
            if tuning_ok:
                if not os.path.exists(choices):
                    print(f"{now()} {root}: tunings done, applying the selection rule", flush=True)
                    with open(os.path.join(root, "logs", "selection.log"), "w") as log:
                        subprocess.run([sys.executable, os.path.join(REPO, "sbcr", "select_configuration.py"),
                                        "--root", root, "--arm", "mg"],
                                       stdout=log, stderr=subprocess.STDOUT, check=True)
                groups += [(s, evaluations_of(root, s)) for s in seeds]
            for seed, group in groups:
                left = 0
                for t in group:
                    key = (root, t["label"])
                    proc = launched.get(key)
                    if (proc is not None and proc.poll() is None) or running(t, procs):
                        in_progress += 1; left += 1
                        active.append(t)
                        continue
                    if proc is not None:  # finished since the last round
                        del launched[key]
                        log_event(root, f"{t['label']},end,{now()},exit {proc.returncode}")
                        if not done(t):
                            failures[key] = failures.get(key, 0) + 1
                            print(f"{now()} FAILED {root} {t['label']} (exit {proc.returncode})", flush=True)
                    if done(t):
                        continue
                    left += 1
                    if failures.get(key, 0) >= args.failures:
                        abandoned += 1
                        continue
                    pending.append(t)
                if seed is not None and left == 0:
                    open(evaluation_marker(root, seed), "w").write(now() + "\n")
                    print(f"{now()} {root}: SBCR evaluations with seed {seed} done", flush=True)

        load = os.getloadavg()
        if args.list_only:
            print(f"in progress: {in_progress}   pending: {len(pending)}   slots taken: {len(procs)}   "
                  f"load: {load[0]:.1f} (max {args.max_load:g})")
            for t in sorted(pending, key=lambda t: -t["cost"]):
                print(f"  {t['root']}  {t['label']}  {' '.join(t['argv'][1:])}  ~{t['cost']/3600:.1f} h")
            return
        if not pending and in_progress == 0:
            break

        for root in roots:
            log_load(root, load, len(procs))
        if args.max_load > 0 and load[0] > args.max_load:
            if active and overloaded_since is None:
                overloaded_since = time.time()
                print(f"{now()} load {load[0]:.1f} above {args.max_load:g} with {len(active)} task(s) running",
                      flush=True)
            if active and time.time() - overloaded_since >= args.overload_minutes * 60:
                # A run under this load completes fewer iterations per conflict, so it is discarded.
                for t in active:
                    key = (t["root"], t["label"])
                    proc = launched.pop(key, None)
                    for pid in task_pids(t, procs):
                        kill_task_process(pid)
                    if proc is not None:
                        kill_task_process(proc.pid)
                        proc.wait()
                    log_event(t["root"], f"{t['label']},end,{now()},killed: load {load[0]:.1f} above "
                                         f"{args.max_load:g} for {args.overload_minutes:g} min")
                    print(f"{now()} killed {t['root']} {t['label']}: load {load[0]:.1f}", flush=True)
                overloaded_since = None
            if not active:
                overloaded_since = None
                print(f"{now()} waiting for CPU: load {load[0]:.1f}, at most {args.max_load:g}", flush=True)
            time.sleep(60)
            continue
        overloaded_since = None

        pending.sort(key=lambda t: -t["cost"])
        free = free_disk_gb(roots[0])
        if free < args.min_disk:
            print(f"{now()} waiting for disk: {free:.0f} GB free, {args.min_disk:.0f} GB needed",
                  flush=True)
            time.sleep(300)
            continue
        taken = len(procs)
        started = 0
        for t in pending:
            if taken >= args.slots:
                break
            # the load average lags the processes just launched, so they are counted by hand
            if args.max_load > 0 and load[0] + started + 1 > args.max_load:
                break
            if os.path.exists(t["folder"]):
                shutil.rmtree(t["folder"])  # partial output of an interrupted run
            log = open(os.path.join(t["root"], "mergeGen", "LOGS", f"{t['label']}.log"), "w")
            env = dict(os.environ, **t["env"])
            launched[(t["root"], t["label"])] = subprocess.Popen(
                [sys.executable] + t["argv"], cwd=os.path.join(t["root"], "sbcr"), env=env,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            log_event(t["root"], f"{t['label']},start,{now()},{' '.join(t['argv'][1:])}")
            print(f"{now()} starts {t['root']} {t['label']} ({' '.join(t['argv'][1:])})", flush=True)
            taken += 1; started += 1
            time.sleep(3)
        time.sleep(60)

    if abandoned:
        print(f"{now()} queue closed with {abandoned} task(s) abandoned after failures", flush=True)
        sys.exit(1)
    print(f"{now()} SBCR queue done", flush=True)


if __name__ == "__main__":
    main()
