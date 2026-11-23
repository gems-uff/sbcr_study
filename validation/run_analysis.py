#!/usr/bin/env python3
"""Runs the analysis scripts of the package on the archives and compares each output with the
archived one.

The archives are extracted into one folder (`--archives`), which the script only reads. It works
on a copy of that folder (`--work`): before each step it removes from the copy the files the step
writes, runs the step, and compares each file the step wrote with the file of the same path in the
archives, by SHA-256. A file whose hash differs is compared by content: a CSV cell by cell (numbers
within a relative tolerance of 1e-9, rows matched by their text columns when the order differs), a
JSON file key by key, and any other text file line by line. A step whose outputs the archives do
not hold (a check that prints its result) has its standard output logged for a reader to compare
with the paper.

Runs in the analysis image (`environments/`), where each step calls the conda environment it
needs. Steps run in order, since later ones read what earlier ones wrote (the similarities feed
the comparisons, the comparisons the spread).

Inputs: the extracted archives (`--archives`), a copy of them (`--work`), a checkout of the
submitted version of this repository (`--submitted`, for the RQ4 lists `build_table.py` reads) and
the folder `codet5-small-local` (`--backbone`, for the token counts).
Outputs: in `--logs`, one log per step (`<step>.log`, its standard output and error), the
comparison of every output (`comparison.tsv`: step, path, result, detail) and a summary
(`summary.txt`).

    python validation/run_analysis.py --archives /data --work /work-copy --submitted /submitted \
        --backbone /backbone/codet5-small-local --logs /out/logs [--only <step> ...]
"""
import argparse
import csv
import glob
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import time

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = {env: ["conda", "run", "--no-capture-output", "-n", env, "python"]
      for env in ("sbcr-analysis", "mergegen-train")}
RSCRIPT = ["conda", "run", "--no-capture-output", "-n", "winner-model", "Rscript"]
SEEDS = "partition-1-sbcr-seeds"
WINNER2 = "winner-model-two-predictors"
WINNER3 = "winner-model-three-predictors"


def script(path):
    return os.path.join(PACKAGE, path)


def steps(W, SUB):
    """Each step: name, command, the paths it writes (globs, relative to the work copy), the file
    its standard output goes to (relative to the work copy, or None), and, for outputs written to
    a new folder, a map from that folder to the archived one."""
    sa, mt = PY["sbcr-analysis"], PY["mergegen-train"]
    data = f"{W}/datasets/source"
    parts = " ".join(f"--partition {n}={W}/partition-{n}" for n in (1, 2, 3)).split()
    refs = " ".join(f"--ref p{n}={W}/partition-{n}" for n in (1, 2, 3)).split()
    S = []

    def add(name, cmd, writes, stdout=None, moved=None):
        S.append({"name": name, "cmd": cmd, "writes": writes, "stdout": stdout, "moved": moved or {}})

    # similarities and comparisons of each root that has candidates of both approaches
    for root in ("partition-1", "partition-2", "partition-3", "chronological", "split-comparison"):
        logs = f"{root}/logs" if root != "split-comparison" else None
        add(f"{root}:mergegen_similarity", sa + [script("analysis/similarity/mergegen_similarity.py"), "--root", f"{W}/{root}"],
            [f"{root}/mergeGen/JIT/*/model_*/similarities.csv"], logs and f"{logs}/similarity_mergegen.log")
        add(f"{root}:sbcr_similarity", sa + [script("analysis/similarity/sbcr_similarity.py"), "--root", f"{W}/{root}"],
            [f"{root}/sbcr_similarities.csv"], logs and f"{logs}/similarity_sbcr.log")
        add(f"{root}:compare_approaches", sa + [script("analysis/rq1_rq3/compare_approaches.py"), "--root", f"{W}/{root}"],
            [f"{root}/comparison.csv", f"{root}/seed_spread.csv"], logs and f"{logs}/consolidate.log")

    # SBCR seeds of partition 1
    add(f"{SEEDS}:sbcr_similarity", sa + [script("analysis/similarity/sbcr_similarity.py"), "--root", f"{W}/{SEEDS}"],
        [f"{SEEDS}/sbcr_similarities.csv"], f"{SEEDS}/logs/similarity_sbcr.log")
    add(f"{SEEDS}:compare_approaches", sa + [script("analysis/rq1_rq3/compare_approaches.py"), "--root", f"{W}/{SEEDS}"],
        [f"{SEEDS}/comparison.csv", f"{SEEDS}/seed_spread.csv"], f"{SEEDS}/logs/consolidate.log")
    add(f"{SEEDS}:seed_spread", sa + [script("analysis/rq1_rq3/seed_spread.py"), "--root", f"{W}/{SEEDS}"],
        [f"{SEEDS}/comparison_per_seed.csv", f"{SEEDS}/seed_summary.csv"], f"{SEEDS}/logs/seed_spread.log")

    # spread across the partitions, leakage and project-disjoint comparisons
    add("partition_spread", sa + [script("analysis/rq1_rq3/partition_spread.py")] + parts + ["--out", f"{W}/partition-spread"],
        ["partition-spread/comparison_per_partition.csv", "partition-spread/partition_spread.csv"],
        "partition-spread/spread.log")
    add("partition-spread:leakage_effect", sa + [script("analysis/rq1_rq3/leakage_effect.py"), "--root", f"{W}/split-comparison",
                                                 "--mg-root", f"{W}/partition-1", "--out", f"{W}/partition-spread/common_set"],
        ["partition-spread/common_set/*.csv"], "partition-spread/common_set.log")
    add("split-comparison:leakage_effect", sa + [script("analysis/rq1_rq3/leakage_effect.py"), "--root", f"{W}/split-comparison",
                                                 "--out", f"{W}/split-comparison"],
        ["split-comparison/leakage_effect.csv", "split-comparison/common_set.csv"], "split-comparison/leakage_effect.log")
    add("split-comparison:leakage_effect partition-1", sa + [
        script("analysis/rq1_rq3/leakage_effect.py"), "--root", f"{W}/split-comparison", "--mg-root", f"{W}/partition-1",
        "--out", f"{W}/split-comparison/partition-1"],
        ["split-comparison/partition-1/leakage_effect.csv", "split-comparison/partition-1/common_set.csv"],
        "split-comparison/partition-1/leakage_effect.log")
    pdc = "project-disjoint-comparison"
    add(f"{pdc}:split-comparison", sa + [script("analysis/rq1_rq3/project_disjoint_comparison.py"), "--root", f"{W}/split-comparison",
                                         "--out", f"{W}/{pdc}/run-split-comparison"],
        [f"{pdc}/run-split-comparison/*"], f"{pdc}/run-split-comparison.log")
    add(f"{pdc}:partition-1", sa + [script("analysis/rq1_rq3/project_disjoint_comparison.py"), "--root", f"{W}/split-comparison",
                                    "--mg-root", f"{W}/partition-1", "--out", f"{W}/{pdc}/run-partition-1"],
        [f"{pdc}/run-partition-1/*"], f"{pdc}/run-partition-1.log")
    add(f"{pdc}:whole test, seed 3022024", sa + [script("analysis/rq1_rq3/compare_approaches.py"), "--root", f"{W}/split-comparison",
                                                 "--out", f"{W}/{pdc}/whole-test/seed-3022024", "--seeds", "3022024"],
        [f"{pdc}/whole-test/seed-3022024/*"], f"{pdc}/whole-test-seed-3022024.log")
    add(f"{pdc}:whole test, five seeds", sa + [script("analysis/rq1_rq3/compare_approaches.py"), "--root", f"{W}/split-comparison",
                                               "--out", f"{W}/{pdc}/whole-test/five-seeds"],
        [f"{pdc}/whole-test/five-seeds/*"], f"{pdc}/whole-test-five-seeds.log")

    # counts, times and sizes of partition 1
    p1 = f"{W}/partition-1"
    add("partition-1:population_tokens", mt + [script("analysis/datasets/population_tokens.py"), "--root", p1, "--arms", "mg"],
        ["partition-1/population_tokens.csv"])
    add("partition-1:population_candidates", sa + [script("analysis/datasets/population_candidates.py"), "--root", p1,
                                                    "--arms", "mg", "--seeds", "3022024"],
        ["partition-1/population_candidates.csv", "partition-1/population_sizes.csv"])
    add("partition-1:tabulate_population", sa + [script("analysis/datasets/tabulate_population.py"), "--root", p1],
        ["partition-1/population_table.csv"], "partition-1/logs/tabulate_population.log")
    add("partition-1:times_per_language", sa + [script("analysis/rq1_rq3/times_per_language.py"), "--root", p1],
        ["partition-1/times_per_language.csv"], "partition-1/logs/times_per_language.log")
    add("partition-1:partition_sizes", sa + [script("analysis/datasets/partition_sizes.py"), "--root", p1],
        ["partition-1/partition_sizes.csv"], "partition-1/logs/partition_sizes.log")

    # RQ3 statistics
    add("rq3_gaps", sa + [script("analysis/rq1_rq3/rq3_gaps.py"), "--root", p1, "--sbcr-seeds", "3022024",
                          "--out", f"{W}/rq3-statistics", "--check-against-comparison"],
        ["rq3-statistics/rq3_gaps_s3022024.csv", "rq3-statistics/rq3_gap_difference_s3022024.csv",
         "rq3-statistics/rq3_gaps_s3022024.json"], "rq3-statistics/rq3_gaps_s3022024.log")

    # chronological split
    dates = f"{W}/commit-dates/universe/commit_dates.csv"
    add("chronological:chronological_effects", sa + [script("analysis/chronological/chronological_effects.py"),
                                                     "--root", f"{W}/chronological"] + refs
        + ["--dates", dates, "--data-root", data, "--out", f"{W}/chronological/effects"],
        ["chronological/effects/*"], "chronological/logs/chrono_effects.log")
    add("commit-dates:temporal_structure", sa + [script("analysis/chronological/temporal_structure.py"), "--root", p1,
                                                 "--dates", dates, "--data-root", data, "--out", f"{W}/commit-dates/partition-1"],
        ["commit-dates/partition-1/*"], "commit-dates/partition-1.log")

    # datasets
    add("resolution_categories", sa + [script("analysis/datasets/resolution_categories.py"), "--data-root", data],
        [], "dataset2-categories/resolution_categories.log")
    add("survey", sa + [script("preparation/survey.py"), "--data-root", data, "--out", f"{W}/dataset-overlap"],
        ["dataset-overlap/*.csv", "dataset-overlap/*.json"], "dataset-overlap/dataset_overlap.log")
    for n in (1, 2, 3):
        add(f"partition-{n}:cap_share", sa + [script("analysis/datasets/cap_share.py"), "--splits", f"{W}/partition-{n}/splits"],
            [], f"validation-printed/cap_share_partition-{n}.txt")
    add("test_overlap", sa + [script("analysis/datasets/test_overlap.py")] + parts, [], "validation-printed/test_overlap.txt")

    # consistency checks
    cc = "consistency-checks"
    add(f"{cc}:shared_commits", sa + [script("analysis/datasets/shared_commits.py"), "--data-root", data]
        + " ".join(f"--root {n}={W}/partition-{n}" for n in (1, 2, 3)).split() + ["--out", f"{W}/{cc}/shared-merge-commits"],
        [f"{cc}/shared-merge-commits/*"], f"{cc}/shared-merge-commits.log")
    add(f"{cc}:largest_test_group", ["bash", "-c",
        " ".join(sa) + f" {script('analysis/datasets/largest_test_group.py')} --splits {W}/split-comparison/splits"
        f" --out {W}/{cc}/largest-test-group/largest_test_group_split-comparison.csv && "
        + " ".join(sa) + f" {script('analysis/datasets/largest_test_group.py')} --splits {p1}/splits --arms pd"
        f" --out {W}/{cc}/largest-test-group/largest_test_group_partition-1_pd.csv"],
        [f"{cc}/largest-test-group/*"], f"{cc}/largest-test-group.log")
    add(f"{cc}:faster_slower_counts", sa + [script("analysis/rq1_rq3/faster_slower_counts.py"), f"{p1}/times_per_language.csv"],
        [], f"{cc}/sbcr-faster-share.log")

    # decoding of MergeGen's candidates
    md = "mergegen-decoding"
    add(f"{md}:decode", ["env", "CUDA_VISIBLE_DEVICES=", "OMP_NUM_THREADS=1"] + mt + [
        script("analysis/datasets/decoding_effect.py"), "decode", "--root", p1,
        "--tokenizer", f"{p1}/mergeGen/codet5-small-local", "--out", f"{W}/{md}"],
        [f"{md}/decoded_candidates.json", f"{md}/decode.json"], f"{md}/decode.log")
    add(f"{md}:measure", ["env", "OMP_NUM_THREADS=1"] + sa + [
        script("analysis/datasets/decoding_effect.py"), "measure", "--root", p1, "--out", f"{W}/{md}",
        "--rq3-gaps", f"{W}/rq3-statistics/rq3_gaps_s3022024.csv"],
        [f"{md}/*.csv", f"{md}/measure.json"], f"{md}/measure.log")

    # the model of the characteristics that predict the winner
    def winner(folder, extra, fits, boots, ties):
        add(f"{folder}:build_table", sa + [script("analysis/winner/build_table.py"), "--root", p1, "--out", f"{W}/{folder}",
                                           "--metadata", data, "--package", SUB] + extra,
            [f"{folder}/*.csv", f"{folder}/build_table.json"])
        for sub, two in fits:
            out = f"{W}/{folder}/{sub}" if sub else f"{W}/{folder}"
            rel = f"{folder}/{sub}" if sub else folder
            add(f"{rel}:fit_models", RSCRIPT + [script("analysis/winner/fit_models.R"), f"{W}/{folder}"]
                + (["--two"] if two else []) + [f"--out={out}"],
                [f"{rel}/coefficients.csv", f"{rel}/cells.csv", f"{rel}/fit.csv", f"{rel}/fit_models.log"],
                f"{rel}/fit_models.stdout")
        for sub, two in boots:
            out = f"{W}/{folder}/{sub}" if sub else f"{W}/{folder}"
            rel = f"{folder}/{sub}" if sub else folder
            add(f"{rel}:bootstrap_main", RSCRIPT + [script("analysis/winner/bootstrap_main.R"), f"{W}/{folder}"]
                + (["--two"] if two else []) + [f"--out={out}"],
                [f"{rel}/bootstrap_main*.csv", f"{rel}/bootstrap_main.log"])
        if ties:
            add(f"{folder}:ties_by_imbalance", sa + [script("analysis/winner/ties_by_imbalance.py"), f"{W}/{folder}"],
                [f"{folder}/ties_by_imbalance.csv"])

    winner(WINNER3, [], [(None, False)], [(None, False)], True)
    winner(f"{WINNER2}/stored", [], [("three", False), ("two", True)], [("two", True)], False)
    winner(f"{WINNER2}/decoded", ["--decoded", f"{W}/{md}/changed_candidates.csv"],
           [("two", True), ("three", False)], [("two", True)], True)

    # RQ4
    scheme = script("analysis/rq4/scheme/coding-scheme.json")
    rq4 = f"{W}/rq4"
    add("rq4:draw_sample", sa + [script("analysis/rq4/draw_sample.py"), "--root", p1, "--out", f"{W}/validation-new/sample",
                                 "--sealed", f"{W}/validation-new/sealed/sealed_sample.csv"],
        ["validation-new/sample/*", "validation-new/sealed/sealed_sample.csv"], None,
        {"validation-new/sample": "rq4/sample", "validation-new/sealed": "rq4/sealed"})
    add("rq4:build_packages", sa + [script("analysis/rq4/build_packages.py"), "--root", p1,
                                    "--sealed", f"{rq4}/sealed/sealed_sample.csv", "--draw", f"{rq4}/sample",
                                    "--data-root", data, "--out", f"{W}/validation-new/sample-packages"],
        ["validation-new/sample-packages/**"], None, {"validation-new/sample-packages": "rq4/sample"})
    add("rq4:build_scale", sa + [script("analysis/rq4/build_scale.py"), "--root", p1, "--data-root", data,
                                 "--sample-draw", f"{rq4}/sample", "--out", f"{W}/validation-new/scale",
                                 "--sealed", f"{W}/validation-new/sealed-scale/sealed_scale.csv"],
        ["validation-new/scale/**", "validation-new/sealed-scale/**"], None,
        {"validation-new/scale": "rq4/scale", "validation-new/sealed-scale": "rq4/sealed/scale"})
    add("rq4:kappa_report", sa + [script("analysis/rq4/agreement/kappa_report.py"), "--draw", f"{rq4}/sample",
                                  "--scheme", scheme, "--sheet", f"{rq4}/coding/coding_sheet.csv",
                                  "--annotator", f"{rq4}/annotator/block1-labeling", "--blocks", "1",
                                  "--out", f"{W}/validation-new/agreement-block1"],
        ["validation-new/agreement-block1/*"], None, {"validation-new/agreement-block1": "rq4/agreement/block1"})
    # the archives hold no report of block 1 until this step writes it from the published coding sheet
    add("rq4:join_scale", sa + [script("analysis/rq4/join_scale.py"), "--sealed", f"{rq4}/sealed/scale/sealed_scale.csv",
                                "--draw", f"{rq4}/scale", "--scheme", scheme,
                                "--description", f"{rq4}/annotator/scale-description",
                                "--labeling", f"{rq4}/annotator/scale-labeling",
                                "--sheet", f"{rq4}/coding/coding_sheet.csv",
                                "--approval", f"{rq4}/annotator/block1-labeling",
                                "--sample-sealed", f"{rq4}/sealed/sealed_sample.csv",
                                "--out", f"{W}/validation-new/join"],
        ["validation-new/join/*"], None, {"validation-new/join": "rq4/sealed/scale/join"})
    add(f"{cc}:band_code_checks", sa + [script("analysis/rq4/band_code_checks.py"),
                                        "--joined", f"{rq4}/sealed/scale/join/joined.csv",
                                        "--tokens", f"{p1}/population_tokens.csv",
                                        "--out", f"{W}/{cc}/band-codes-against-limits"],
        [f"{cc}/band-codes-against-limits/*"], f"{cc}/band-codes-against-limits.log")
    add("rq4:sbcr_candidate_origin", sa + [script("analysis/rq4/sbcr_candidate_origin.py"), "--root", p1,
                                           "--joined", f"{rq4}/sealed/scale/join/joined.csv",
                                           "--out", f"{W}/validation-new/sbcr-candidate-origin"],
        ["validation-new/sbcr-candidate-origin/*"], None,
        {"validation-new/sbcr-candidate-origin": "rq4/sealed/sbcr-candidate-origin"})

    # figures: the archives do not hold them, so they are written for a reader to compare with the paper
    add("figures", sa + [script("analysis/figures/paper_figures.py"), "--root", p1, "--scale", f"{rq4}/scale",
                         "--out", f"{W}/validation-new/figures"],
        ["validation-new/figures/*"], "validation-printed/figures.txt")
    return S


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def expand(work, patterns):
    found = set()
    for pat in patterns:
        for p in glob.glob(os.path.join(work, pat), recursive=True):
            if os.path.isfile(p):
                found.add(os.path.relpath(p, work))
    return sorted(found)


def archived_path(rel, moved):
    for new, old in moved.items():
        if rel == new or rel.startswith(new + "/"):
            return old + rel[len(new):]
    return rel


# ---- comparison by content -------------------------------------------------------------------

def number(text):
    try:
        v = float(text)
    except ValueError:
        return None
    return v if text.strip() not in ("", "nan", "NaN") or math.isnan(v) else None


def close(a, b, rel=1e-9):
    if a == b or (math.isnan(a) and math.isnan(b)):
        return True, 0.0
    d = abs(a - b)
    return d <= rel * max(abs(a), abs(b), 1e-300), d


def compare_csv(new, old):
    rn = list(csv.reader(io.StringIO(open(new, encoding="utf-8", newline="").read())))
    ro = list(csv.reader(io.StringIO(open(old, encoding="utf-8", newline="").read())))
    if not rn or not ro:
        return "empty file", False
    if rn[0] != ro[0]:
        if sorted(rn[0]) != sorted(ro[0]):
            return f"columns differ: {rn[0]} vs {ro[0]}", False
        idx = [rn[0].index(c) for c in ro[0]]
        rn = [[r[i] for i in idx] for r in rn]
    if len(rn) != len(ro):
        return f"{len(rn) - 1} rows vs {len(ro) - 1} archived", False
    body_n, body_o = rn[1:], ro[1:]
    if body_n != body_o and sorted(body_n) == sorted(body_o):
        return "same rows in another order", True
    order = ""
    if body_n != body_o:
        text_cols = [i for i in range(len(ro[0])) if any(number(r[i]) is None and r[i] != "" for r in body_o)]
        key = lambda r: tuple(r[i] for i in text_cols)  # noqa: E731
        if sorted(map(key, body_n)) == sorted(map(key, body_o)) and len(set(map(key, body_o))) == len(body_o):
            body_n, body_o = sorted(body_n, key=key), sorted(body_o, key=key)
            order = "rows in another order; "
    worst, cells, unequal = 0.0, 0, []
    for rn_, ro_ in zip(body_n, body_o):
        for c, (a, b) in enumerate(zip(rn_, ro_)):
            if a == b:
                continue
            x, y = number(a), number(b)
            if x is None or y is None:
                unequal.append(f"{ro[0][c]}: {a!r} vs {b!r}")
                continue
            ok, d = close(x, y)
            worst = max(worst, d)
            cells += not ok
            if not ok:
                unequal.append(f"{ro[0][c]}: {a} vs {b}")
    if unequal:
        return order + f"{len(unequal)} cells differ, largest numeric difference {worst:.3g}; first: " + "; ".join(unequal[:5]), False
    return order + (f"same numbers, written differently (largest difference {worst:.3g})" if worst else "same content"), True


def flatten(v, prefix=""):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from flatten(x, f"{prefix}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from flatten(x, f"{prefix}[{i}]")
    else:
        yield prefix, v


def compare_json(new, old):
    try:
        a, b = dict(flatten(json.load(open(new, encoding="utf-8")))), dict(flatten(json.load(open(old, encoding="utf-8"))))
    except (ValueError, UnicodeDecodeError):
        return compare_text(new, old)
    diff = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k, "<missing>"), b.get(k, "<missing>")
        if x == y:
            continue
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and close(float(x), float(y))[0]:
            continue
        diff.append(f"{k}: {str(x)[:80]!r} vs {str(y)[:80]!r}")
    if diff:
        return f"{len(diff)} keys differ; " + "; ".join(diff[:6]), False
    return "same content", True


def compare_text(new, old):
    try:
        a = open(new, encoding="utf-8").read().splitlines()
        b = open(old, encoding="utf-8").read().splitlines()
    except UnicodeDecodeError:
        return "binary file, different bytes", False
    if a == b:
        return "same lines (line endings differ)", True
    strip = lambda lines: lines[:len(lines) - next((i for i, l in enumerate(reversed(lines)) if l.strip()), len(lines))]  # noqa: E731
    if strip(a) == strip(b):
        return "same lines (blank lines at the end differ)", True
    import difflib
    d = [l for l in difflib.unified_diff(b, a, "archived", "new", n=0, lineterm="") if not l.startswith(("---", "+++", "@@"))]
    return f"{sum(l.startswith('-') for l in d)} lines archived only, {sum(l.startswith('+') for l in d)} new only; " + \
        " | ".join(l[:160] for l in d[:8]), False


def compare(new, old):
    if not os.path.exists(old):
        return "not in the archives", None
    if sha256(new) == sha256(old):
        return "", True
    if new.endswith(".csv"):
        return compare_csv(new, old)
    if new.endswith(".json"):
        return compare_json(new, old)
    return compare_text(new, old)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--archives", required=True, help="the four archives, extracted into one folder (read only)")
    p.add_argument("--work", required=True, help="a copy of that folder, where the steps write")
    p.add_argument("--submitted", required=True, help="checkout of the submitted version of this repository")
    p.add_argument("--backbone", required=True, help="folder codet5-small-local")
    p.add_argument("--logs", required=True, help="folder of the logs of this run")
    p.add_argument("--only", nargs="*", help="run only the steps whose name starts with one of these")
    args = p.parse_args()

    A, W = os.path.abspath(args.archives), os.path.abspath(args.work)
    os.makedirs(args.logs, exist_ok=True)
    backbone = f"{W}/partition-1/mergeGen/codet5-small-local"
    if not os.path.exists(backbone):
        shutil.copytree(args.backbone, backbone)

    # the root of the SBCR seeds reads the data and the MergeGen outputs of partition 1
    for sub in ("data", "mergeGen"):
        link = f"{W}/{SEEDS}/{sub}"
        if not os.path.lexists(link):
            os.symlink(f"../partition-1/{sub}", link)

    table = open(os.path.join(args.logs, "comparison.tsv"), "a", encoding="utf-8")
    summary = []
    for step in steps(W, os.path.abspath(args.submitted)):
        if args.only and not any(step["name"].startswith(o) for o in args.only):
            continue
        for rel in expand(W, step["writes"]):
            os.remove(os.path.join(W, rel))
        log = os.path.join(args.logs, step["name"].replace("/", "_").replace(":", "__").replace(" ", "_").replace(",", "") + ".log")
        start = time.time()
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("$ " + " ".join(step["cmd"]) + "\n\n")
            fh.flush()
            r = subprocess.run(step["cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=PACKAGE)
            out = r.stdout.decode("utf-8", "replace")
            fh.write(out)
            fh.write(f"\nexit {r.returncode}, {time.time() - start:.0f} s\n")
        if step["stdout"]:
            dest = os.path.join(W, step["stdout"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(r.stdout)
        written = expand(W, step["writes"]) + ([step["stdout"]] if step["stdout"] else [])
        counts = {"equal": 0, "same content": 0, "differs": 0, "not archived": 0}
        for rel in written:
            old = os.path.join(A, archived_path(rel, step["moved"]))
            detail, ok = compare(os.path.join(W, rel), old)
            kind = "not archived" if ok is None else "equal" if ok and not detail else "same content" if ok else "differs"
            counts[kind] += 1
            table.write(f"{step['name']}\t{rel}\t{kind}\t{detail}\n")
        table.flush()
        # archived files a step should have written and did not
        back = {old: new for new, old in step["moved"].items()}
        archived = expand(A, [archived_path(w, step["moved"]) for w in step["writes"]])
        written_as_archived = {archived_path(rel, step["moved"]) for rel in written}
        missing = [f for f in archived if f not in written_as_archived]
        missing = [f for f in missing if not step["moved"] or any(f.startswith(o + "/") for o in back)]
        line = (f"{step['name']}: exit {r.returncode}, {len(written)} files, "
                + ", ".join(f"{v} {k}" for k, v in counts.items() if v)
                + (f", {len(missing)} archived files not written" if missing else ""))
        for m in missing:
            table.write(f"{step['name']}\t{m}\tnot written\t\n")
        print(line, flush=True)
        summary.append(line)
    with open(os.path.join(args.logs, "summary.txt"), "a", encoding="utf-8") as fh:
        fh.write("\n".join(summary) + "\n")


if __name__ == "__main__":
    main()
