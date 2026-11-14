#!/usr/bin/env python3
"""Agreement report of the RQ4 coding, block by block. Python 3.8 or later, standard library only.

For each block and each dimension of the frozen scheme:

- the kappa between the authors' consensus and the automatic annotator, over the cases with
  consensus, with raw agreement beside it. Its observed value decides whether the annotator is
  approved (0.61 or above in every dimension), except in the pilot, which counts for nothing;
- the worst-case kappa, over every case of the block, in which a case without consensus counts as
  a disagreement: its human label is the authors' reading that differs from the annotator's label
  and, if both differ, the first author's;
- each of the two with a 95% percentile bootstrap interval, 2,000 resamples of cases, with the
  seed `SEED`, drawn with `secrets.randbelow` before any block was measured. Every interval starts
  a new generator with that seed, so a number does not depend on the other blocks or dimensions;
- per category, over the cases with consensus, how many cases the authors and the annotator gave
  it and in how many both did. The predefined values (*no candidate*, *no difference between the
  candidates*, *neither candidate clearly further from the resolution*) are flagged rows;
- the cases with an empty candidate and with identical candidates, read from the packages, and
  the agreement on them;
- if the labeling ran more than once on the block, the agreement of each later run with run 1.
  Only run 1 enters the kappa, so that no run is chosen after its result is seen.

A kappa whose expected agreement is 1 (every label of both sides in one category) is taken as 1.

Inputs:

- `--draw`: the folder with `coding_sheet.csv` and `packages/<case>.md`, as `run_annotator.py`
  reads it. A folder that holds the sealed file is refused. Block 0 is the pilot (role `pilot`);
  every other block counts for the decision (role `sample`), and any other role is refused. A
  package has an empty candidate when it shows a candidate as *(empty)* or *(whitespace only)* and
  neither version is empty; when a version is empty, an empty candidate is the text of that
  version. A package has identical candidates when both have code and are equal once all
  whitespace is removed, or when both are empty and a version is empty.
- `--scheme`: the frozen scheme, `{"version": ..., "dimensions": [{"id": ..., "name": ...,
  "categories": [{"code": ..., "name": ..., "definition": ..., "predefined": ..., "residual": ...}]}]}`.
- `--sheet`: the coding sheet, one row per case, with, for each dimension id `<d>`:
  `dominant_code_<d>`, the consensus; `no_consensus_<d>`, `1` when the authors did not reach
  consensus and empty otherwise; and `reading_author1_<d>` and `reading_author2_<d>`, each
  author's final position after a discussion that ended without consensus. `author1` is the first
  author of the paper. Labels are category codes.
- `--annotator`: the folder of the labeling step of `run_annotator.py`, `<case>/run<k>.json` with
  `"step": "labeling"` and the model's answer in `output` (`code`, or `code_<d>` per dimension,
  holding the code or the name of the category). All run-1 records of a block must carry the same
  instructions, scheme and description instructions.
- `--blocks`: the blocks to measure, for example `1`, or `0` for the pilot.

Outputs: `kappa_report.md` and `kappa_report.json` in `--out`, which must not hold a report yet;
the Markdown is also printed.

    python analysis/rq4/agreement/kappa_report.py --draw <sample folder> --scheme <scheme.json> \
        --sheet <coding sheet> --annotator <labeling folder of block 1> --blocks 1 --out <dir>
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from packages import PackageError, check_draw_folder, parse_package  # noqa: E402
THRESHOLD = 0.61
RESAMPLES = 2000
SEED = 559479682
COUNTED_RUN = 1
DIM_ID = re.compile(r"^[A-Za-z0-9_]+$")
RUN_FILE = re.compile(r"^run(\d+)\.json$")


class InputError(Exception):
    pass


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# --- measures ---------------------------------------------------------------------------

def kappa(pairs):
    """Cohen's kappa of a list of (label, label) pairs; None for no pairs."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(left[c] * right[c] for c in left) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def percentile(values, p):
    """Linear interpolation between the closest ranks, as numpy.percentile does by default."""
    xs = sorted(values)
    h = (len(xs) - 1) * p / 100
    lo = math.floor(h)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


def bootstrap(pairs, resamples=RESAMPLES, seed=SEED):
    n = len(pairs)
    if not n:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        values.append(kappa([pairs[int(rng.random() * n)] for _ in range(n)]))
    return [percentile(values, 2.5), percentile(values, 97.5)]


def measure(pairs):
    agree = sum(a == b for a, b in pairs)
    return {"cases": len(pairs), "agreements": agree,
            "raw_agreement": agree / len(pairs) if pairs else None,
            "kappa": kappa(pairs), "ci95": bootstrap(pairs)}


def worst_case_label(reading1, reading2, annotator):
    """The human label of a case without consensus in the worst-case kappa."""
    return reading1 if reading1 != annotator else reading2


# --- inputs -----------------------------------------------------------------------------

def load_scheme(path):
    with open(path, encoding="utf-8") as fh:
        scheme = json.load(fh)
    dims = scheme.get("dimensions")
    if not isinstance(dims, list) or len(dims) not in (1, 2):
        raise InputError(f"{path}: the scheme needs one or two dimensions")
    out, seen = [], set()
    for d in dims:
        did = d.get("id", "")
        if not DIM_ID.match(did) or did in seen:
            raise InputError(f"{path}: dimension id {did!r} missing, repeated or not made of letters, digits and _")
        seen.add(did)
        cats = d.get("categories") or []
        codes = [c.get("code", "") for c in cats]
        names = [c.get("name", "") for c in cats]
        if not cats or "" in codes or len(set(codes)) != len(codes) or len(set(names)) != len(names):
            raise InputError(f"{path}: dimension {did}: categories missing, or a code missing or repeated, "
                             "or a name repeated")
        clash = {c["code"] for c in cats for o in cats if o is not c and c["code"] == o["name"]}
        if clash:
            raise InputError(f"{path}: dimension {did}: {sorted(clash)} is the code of one category and the "
                             "name of another")
        out.append({"id": did, "name": d.get("name", did),
                    "categories": [{"code": c["code"], "name": c["name"], "predefined": bool(c.get("predefined")),
                                    "residual": bool(c.get("residual"))} for c in cats],
                    "codes": set(codes), "by_name": {c["name"]: c["code"] for c in cats}})
    return scheme.get("version", ""), out


def package_flags(p):
    """(empty candidate, identical candidates) of a parsed package.

    An empty candidate counts only when neither version is empty: when a version is empty, an
    empty candidate is the text of that version, and two empty candidates are the same text. A version is empty when its conflict marker says *(empty)*,
    the field `empty_versions` of the annotator's description, which also holds when the split
    of the conflict is ambiguous and `v1` and `v2` are None.
    """
    a_empty, b_empty = p["cand_a_state"] != "text", p["cand_b_state"] != "text"
    lines = p["conflict"].split("\n")
    version_empty = lines[0].endswith("(empty)") or lines[-1].endswith("(empty)")
    if a_empty or b_empty:
        return not version_empty, a_empty and b_empty and version_empty
    return False, re.sub(r"\s", "", p["cand_a"]) == re.sub(r"\s", "", p["cand_b"])


def load_draw(draw, blocks):
    check_draw_folder(draw)
    with open(os.path.join(draw, "coding_sheet.csv"), encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if int(r["block"]) in blocks]
    found = {int(r["block"]) for r in rows}
    if found != set(blocks):
        raise InputError(f"blocks not in the coding sheet of the draw: {sorted(set(blocks) - found)}")
    for r in rows:
        expected = "pilot" if int(r["block"]) == 0 else "sample"
        if r["role"] != expected:
            raise InputError(f"case {r['case']} of block {r['block']} has the role {r['role']!r} in the coding sheet "
                             f"of the draw, and a case of that block must have the role {expected!r}")
    rows.sort(key=lambda r: (int(r["block"]), int(r["position"])))
    cases = []
    for r in rows:
        path = os.path.join(draw, "packages", f"{r['case']}.md")
        with open(path, encoding="utf-8") as fh:
            p = parse_package(fh.read(), r["case"])
        if p["case"] != r["case"]:
            raise InputError(f"{path} is titled case {p['case']}")
        empty, same = package_flags(p)
        cases.append({"case": r["case"], "role": r["role"], "block": int(r["block"]),
                      "empty_candidate": empty, "identical_candidates": same})
    return cases


def sheet_columns(dims):
    cols = ["case", "role", "block"]
    for d in dims:
        cols += [f"{k}_{d['id']}" for k in ("dominant_code", "no_consensus", "reading_author1", "reading_author2")]
    return cols


def load_sheet(path, dims, cases):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in sheet_columns(dims) if c not in (reader.fieldnames or [])]
        if missing:
            raise InputError(f"{path}: columns missing: {missing}")
        rows = {}
        for r in reader:
            if r["case"] in rows:
                raise InputError(f"{path}: case {r['case']} appears twice")
            rows[r["case"]] = r
    human = {}
    for c in cases:
        r = rows.get(c["case"])
        if r is None:
            raise InputError(f"{path}: case {c['case']} of block {c['block']} is not in the sheet")
        if r["role"] != c["role"] or str(r["block"]).strip() != str(c["block"]):
            raise InputError(f"{c['case']}: role and block {r['role']}/{r['block']} in the sheet, "
                             f"{c['role']}/{c['block']} in the draw")
        human[c["case"]] = {d["id"]: human_labels(r, d, c["case"]) for d in dims}
    return human


def human_labels(row, dim, case):
    did, codes = dim["id"], dim["codes"]
    get = {k: (row[f"{k}_{did}"] or "").strip() for k in ("dominant_code", "no_consensus", "reading_author1",
                                                          "reading_author2")}
    where = f"{case}, dimension {did}"
    if get["no_consensus"] not in ("", "1"):
        raise InputError(f"{where}: no_consensus is {get['no_consensus']!r}, and must be 1 or empty")
    if get["no_consensus"] == "1":
        if get["dominant_code"]:
            raise InputError(f"{where}: a case without consensus has a dominant code")
        for k in ("reading_author1", "reading_author2"):
            if get[k] not in codes:
                raise InputError(f"{where}: case without consensus, {k} {get[k]!r} is not a code of the scheme")
        if get["reading_author1"] == get["reading_author2"]:
            raise InputError(f"{where}: case without consensus, but both readings are {get['reading_author1']!r}")
    else:
        if get["dominant_code"] not in codes:
            raise InputError(f"{where}: dominant_code {get['dominant_code']!r} is not a code of the scheme")
        if get["reading_author1"] or get["reading_author2"]:
            raise InputError(f"{where}: a case with consensus has readings, which are only for cases without it")
    return {"consensus": get["dominant_code"] or None,
            "readings": (get["reading_author1"], get["reading_author2"]) if get["no_consensus"] else None}


def annotator_code(output, dim, single, where):
    field = "code" if single else f"code_{dim['id']}"
    value = output.get(field)
    if value in dim["codes"]:
        return value
    if value in dim["by_name"]:
        return dim["by_name"][value]
    raise InputError(f"{where}: {field} {value!r} is neither a code nor a name of the scheme")


def load_annotator(folder, dims, cases):
    single = len(dims) == 1
    labels, versions = {}, {}
    for c in cases:
        runs = {}
        for path in sorted(glob.glob(os.path.join(folder, c["case"], "run*.json"))):
            m = RUN_FILE.match(os.path.basename(path))
            if not m:
                continue
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
            where = os.path.relpath(path, folder)
            if rec.get("step") != "labeling":
                raise InputError(f"{where}: step {rec.get('step')!r}; give the folder of the labeling step")
            out = rec.get("output") or {}
            if out.get("case") != c["case"]:
                raise InputError(f"{where}: the answer names case {out.get('case')!r}")
            k = int(m.group(1))
            runs[k] = {d["id"]: annotator_code(out, d, single, where) for d in dims}
            if k == COUNTED_RUN:
                versions.setdefault(c["block"], {}).setdefault(
                    (rec.get("instructions_sha256"), rec.get("instructions_commit"), rec.get("model_requested"),
                     rec.get("effort"), rec.get("scheme_sha256"), rec.get("description_instructions_sha256")),
                    []).append(c["case"])
        if COUNTED_RUN not in runs:
            raise InputError(f"{c['case']}: no run {COUNTED_RUN} of the labeling step in {folder}")
        labels[c["case"]] = runs
    for block, found in versions.items():
        if len(found) > 1:
            raise InputError(f"block {block}: run {COUNTED_RUN} was labeled with {len(found)} different "
                             "instructions, models, schemes or descriptions, and a block is labeled with one frozen version")
    keys = ("instructions_sha256", "instructions_commit", "model", "effort", "scheme_sha256",
            "description_instructions_sha256")
    return labels, {b: dict(zip(keys, next(iter(f)))) for b, f in versions.items()}


# --- report -----------------------------------------------------------------------------

def block_report(block, cases, dims, human, annot, version):
    counts = block != 0
    out = {"block": block, "counts_for_the_decision": counts, "cases": len(cases), "annotator": version,
           "dimensions": {}}
    for d in dims:
        did = d["id"]
        main, worst = [], []
        for c in cases:
            h, m = human[c["case"]][did], annot[c["case"]][COUNTED_RUN][did]
            if h["consensus"]:
                main.append((h["consensus"], m))
                worst.append((h["consensus"], m))
            else:
                worst.append((worst_case_label(*h["readings"], m), m))
        with_consensus = [c for c in cases if human[c["case"]][did]["consensus"]]
        per_category = []
        for cat in d["categories"]:
            code = cat["code"]
            per_category.append({**cat, "authors": sum(h == code for h, _ in main),
                                 "annotator": sum(m == code for _, m in main),
                                 "both": sum(h == code and m == code for h, m in main)})
        subsets = {}
        for key in ("empty_candidate", "identical_candidates"):
            inside = [c for c in cases if c[key]]
            agreed = [c for c in inside if human[c["case"]][did]["consensus"]]
            subsets[key] = {"cases": len(inside), "with_consensus": len(agreed),
                            "agreements": sum(human[c["case"]][did]["consensus"]
                                              == annot[c["case"]][COUNTED_RUN][did] for c in agreed)}
        stability = {}
        later = sorted({k for c in cases for k in annot[c["case"]] if k != COUNTED_RUN})
        for k in later:
            pairs = [(annot[c["case"]][COUNTED_RUN][did], annot[c["case"]][k][did])
                     for c in cases if k in annot[c["case"]]]
            agree = sum(a == b for a, b in pairs)
            stability[k] = {"cases": len(pairs), "agreements": agree, "kappa": kappa(pairs)}
        m = measure(main)
        out["dimensions"][did] = {
            "name": d["name"], "with_consensus": len(with_consensus),
            "without_consensus": len(cases) - len(with_consensus),
            "consensus_vs_annotator": m, "worst_case": measure(worst),
            "reaches_threshold": None if m["kappa"] is None else m["kappa"] >= THRESHOLD,
            "per_category": per_category, "subsets": subsets, "stability_against_run_1": stability}
    flags = [v["reaches_threshold"] for v in out["dimensions"].values()]
    out["annotator_approved"] = all(flags) if counts and None not in flags else None
    return out


def fmt(x, digits=3):
    return "n/a" if x is None else f"{x:.{digits}f}"


def fmt_measure(m):
    ci = m["ci95"]
    return f"{fmt(m['kappa'])} ({fmt(ci[0]) if ci else 'n/a'} to {fmt(ci[1]) if ci else 'n/a'})"


def pct(k, n):
    return f"{k} ({100 * k / n:.0f}%)" if n else str(k)


def render(report):
    lines = ["# Agreement report of the RQ4 coding", "",
             f"Generated on {report['generated']} by `analysis/rq4/agreement/kappa_report.py`. Kappa with a 95% "
             f"percentile bootstrap interval, {RESAMPLES} resamples of cases, seed {SEED}. Annotator: run "
             f"{COUNTED_RUN}. Threshold of the observed kappa: {THRESHOLD}. Scheme version "
             f"{report['inputs']['scheme_version'] or '(none)'}.", "",
             "| block | dimension | cases | without consensus | consensus vs annotator | raw agreement "
             "| worst case | reaches the threshold |",
             "|---|---|---:|---:|---|---:|---|---|"]
    for b in report["blocks"]:
        for did, d in b["dimensions"].items():
            m = d["consensus_vs_annotator"]
            reach = ("does not count (pilot)" if not b["counts_for_the_decision"]
                     else "n/a" if d["reaches_threshold"] is None else "yes" if d["reaches_threshold"] else "no")
            lines.append(f"| {b['block']} | {d['name']} | {b['cases']} | {d['without_consensus']} | "
                         f"{fmt_measure(m)} | {fmt(m['raw_agreement'])} | {fmt_measure(d['worst_case'])} | "
                         f"{reach} |")
    for b in report["blocks"]:
        s = b["annotator"]
        lines += ["", f"## Block {b['block']}", ""]
        if b["counts_for_the_decision"]:
            verdict = {True: "approved", False: "not approved", None: "undefined"}[b["annotator_approved"]]
            lines.append(f"Annotator {verdict} by this block: the observed kappa must reach {THRESHOLD} in every "
                         "dimension.")
        else:
            lines.append("Pilot block: its numbers decide nothing, and its cases are out of the frequencies with the "
                         "authors' labels.")
        lines += ["", f"Annotator: model {s['model']}, effort {s['effort']}, instructions "
                      f"{s['instructions_commit']}, SHA-256 {s['instructions_sha256']}, scheme SHA-256 "
                      f"{s['scheme_sha256']}."]
        for did, d in b["dimensions"].items():
            lines += ["", f"### {d['name']}", "",
                      f"{d['with_consensus']} cases with consensus, {d['without_consensus']} without.", "",
                      "| measure | cases | agreements | raw agreement | kappa (95% CI) |", "|---|---:|---:|---:|---|"]
            for key, label in (("consensus_vs_annotator", "consensus vs annotator"), ("worst_case", "worst case")):
                m = d[key]
                lines.append(f"| {label} | {m['cases']} | {m['agreements']} | {fmt(m['raw_agreement'])} | "
                             f"{fmt_measure(m)} |")
            n = d["with_consensus"]
            lines += ["", f"Per category, over the {n} cases with consensus:", "",
                      "| category | authors | annotator | both |", "|---|---:|---:|---:|"]
            for c in d["per_category"]:
                flag = " (predefined)" if c["predefined"] else " (residual)" if c["residual"] else ""
                lines.append(f"| {c['code']} {c['name']}{flag} | {pct(c['authors'], n)} | {pct(c['annotator'], n)} "
                             f"| {c['both']} |")
            lines.append("")
            for key, label in (("empty_candidate", "an empty candidate and no empty version"),
                               ("identical_candidates", "identical candidates")):
                x = d["subsets"][key]
                lines.append(f"- Cases with {label}: {x['cases']}, {x['with_consensus']} with consensus, "
                             f"agreement on {x['agreements']} of them.")
            for k, x in d["stability_against_run_1"].items():
                lines.append(f"- Run {k} against run {COUNTED_RUN}: same label in {x['agreements']} of {x['cases']} "
                             f"cases, kappa {fmt(x['kappa'])}.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--draw", required=True)
    p.add_argument("--scheme", required=True)
    p.add_argument("--sheet", required=True)
    p.add_argument("--annotator", required=True)
    p.add_argument("--blocks", required=True, help="comma-separated, e.g. 1 or 0 for the pilot")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    blocks = sorted({int(b) for b in args.blocks.split(",")})
    md, js = os.path.join(args.out, "kappa_report.md"), os.path.join(args.out, "kappa_report.json")
    if os.path.exists(md) or os.path.exists(js):
        raise SystemExit(f"{args.out} already holds a report. Nothing was written")
    try:
        version, dims = load_scheme(args.scheme)
        cases = load_draw(args.draw, blocks)
        human = load_sheet(args.sheet, dims, cases)
        annot, versions = load_annotator(args.annotator, dims, cases)
    except (InputError, PackageError) as e:
        raise SystemExit(f"{e}. Nothing was written")
    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {"threshold": THRESHOLD, "resamples": RESAMPLES, "seed": SEED, "counted_run": COUNTED_RUN},
        "inputs": {"scheme_version": version, "scheme_sha256": sha256(args.scheme),
                   "sheet_sha256": sha256(args.sheet),
                   "coding_sheet_sha256": sha256(os.path.join(args.draw, "coding_sheet.csv"))},
        "blocks": [block_report(b, [c for c in cases if c["block"] == b], dims, human, annot, versions[b])
                   for b in blocks]}
    text = render(report)
    os.makedirs(args.out, exist_ok=True)
    with open(js, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
