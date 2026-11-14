#!/usr/bin/env python3
"""Joins the labels of the RQ4 coding at scale with the band and the tool of each case.

Until this script runs, nobody knows the band of a case or which tool produced each of its
candidates. Its outputs name the tool of each case, so they go to a folder that neither the
coders nor the annotator read. Runs in `sbcr-analise`: the packages are read by `parse_package`,
which needs pylcs for a conflict whose split into the two versions is ambiguous.

The frequencies per band are those of the population of the bands in partition 1, since every
conflict of the bands was labeled, and carry no sampling margin; the error left is the
annotator's, measured by the per-category agreement of block 1. The report gives counts and
shares and no interval.

The tool behind each label. The candidate characteristic describes the candidate further from the
resolution, which the annotator takes from the field `closer` of its own description: the further
candidate is the one `closer` does not name, and with `equal` or `unclear` no candidate is further.
The join maps that candidate to its tool through the sealed file, and also gives the candidate
further by the measured similarity, all whitespace removed, so that the two can be compared. A case
with an empty candidate and no empty version (*no candidate*) also gets the tool of the empty
candidate.

Inputs:
- `--sealed`: the sealed file of `build_scale.py`, whose SHA-256 must be the `sealed_sha256` of the
  `draw.json` in `--draw`;
- `--draw`: the folder the annotator read, with `draw.json`, `coding_sheet.csv` and
  `packages/<case>.md`, whose hashes must be those of `draw.json`;
- `--scheme`: the frozen scheme, whose SHA-256 must be `SCHEME_SHA256`, and which every labeling
  record must carry;
- `--description` and `--labeling`: the folders of the two steps of `run_annotator.py`, with
  `<case>/run1.json` for every packaged case;
- `--sheet`, the coding sheet with the authors' consensus of block 1, and `--approval`, the labeling
  folder of block 1 that approved the annotator: optional, and given together;
- `--sample-sealed`: the sealed file of the sample draw, optional, whose SHA-256 must be
  `SAMPLE_SEALED_SHA256`, to give the tool behind the candidates of every package the authors read.

Outputs, in `--out` (outside any Git work tree and every input folder, with no earlier join):
`joined.csv` (per case of the bands: dataset, chunk id, band, `d`, the two similarities, the tool
behind A and B, the annotator's `closer`, the tool of the further candidate by the annotator and by
the similarity, the tool of an empty candidate, the codes, and the case and role in the sample),
`frequencies.csv` (per dimension and code, over all bands, per band, per band and dataset, and per
band and tool of the further candidate), `block1.csv`, `sample_tools.csv` (with `--sample-sealed`),
and `join_report.md` and `join_report.json`. The Markdown is also printed.

    python analysis/rq4/join_scale.py --sealed <sealed_scale.csv> --draw <scale folder> --scheme <scheme.json> \
        --description <description folder> --labeling <labeling folder> --sheet <coding sheet> \
        --approval <labeling folder of block 1> --sample-sealed <sealed_sample.csv> --out <dir>
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "agreement"))
from packages import PackageError, inside_git_work_tree, parse_package  # noqa: E402
from kappa_report import InputError, annotator_code, kappa, load_annotator, load_scheme, package_flags  # noqa: E402
EXPECTED_CASES = 1985
SAMPLE_SEALED_SHA256 = "92a4fa20e17d1a01ba7fa91c3377fe254a84ef0e9a4d5a1464a89c10042001d2"
SCHEME_SHA256 = "38f1ae6b1bcd8774c7545149c0f7b3868b3748bf6e778d9e3bb304f7030863a6"
BANDS = ("sbcr", "mergegen", "tie")
BAND_NAMES = {"sbcr": "clear SBCR win", "mergegen": "clear MergeGen win", "tie": "near tie"}
TOOLS = ("sbcr", "mergegen")
TOOL_NAMES = {"sbcr": "SBCR", "mergegen": "MergeGen", "equal": "neither (equal)", "unclear": "neither (unclear)",
              "": "none"}
FURTHER = ("sbcr", "mergegen", "equal", "unclear")
SEALED_COLUMNS = ["case", "dataset", "chunk_id", "band", "d", "sim_sbcr", "sim_mergegen", "candidate_a",
                  "candidate_b", "sbcr_out_of_limits", "packaged", "draw_case", "draw_role"]
BOOL = {"True": True, "False": False}
SAMPLE_COLUMNS = ["case", "role", "block", "candidate_a", "candidate_b"]
OUTPUTS = ("joined.csv", "frequencies.csv", "block1.csv", "sample_tools.csv", "join_report.md", "join_report.json")


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def packages_sha256(folder):
    """SHA-256 of the list `<sha256>  <case>.md` of the packages, as `run_scale.sh` computes it."""
    names = sorted(n for n in os.listdir(folder) if n.endswith(".md"))
    return sha256_text("".join(f"{sha256_file(os.path.join(folder, n))}  {n}\n" for n in names))


def git_state():
    """Commit of the checkout that holds this script, and whether tracked files differ from it."""
    try:
        commit = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        changes = subprocess.run(["git", "-C", HERE, "status", "--porcelain", "--untracked-files=no"],
                                 capture_output=True, text=True, check=True).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None, None
    return commit, bool(changes)


def inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder + os.sep)


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], list(reader)


def write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# --- inputs -----------------------------------------------------------------------------

def load_sealed(path, draw, expected_cases):
    with open(os.path.join(draw, "draw.json"), encoding="utf-8") as fh:
        record = json.load(fh)
    if sha256_file(path) != record.get("sealed_sha256"):
        raise InputError(f"{path} does not have the SHA-256 that {draw}/draw.json records for the sealed file")
    if sha256_file(os.path.join(draw, "coding_sheet.csv")) != record.get("coding_sheet_sha256"):
        raise InputError(f"{draw}/coding_sheet.csv does not have the SHA-256 that draw.json records")
    if packages_sha256(os.path.join(draw, "packages")) != record.get("packages_sha256"):
        raise InputError(f"the packages in {draw}/packages are not those that draw.json records")
    columns, rows = read_csv(path)
    missing = [c for c in SEALED_COLUMNS if c not in columns]
    if missing:
        raise InputError(f"{path}: columns missing: {missing}")
    cases = {}
    for r in rows:
        where = f"{path}, case {r['case']}"
        if r["case"] in cases:
            raise InputError(f"{where} appears twice")
        if r["band"] not in BANDS:
            raise InputError(f"{where}: band {r['band']!r}")
        if {r["candidate_a"], r["candidate_b"]} != set(TOOLS):
            raise InputError(f"{where}: candidates {r['candidate_a']!r} and {r['candidate_b']!r}")
        for k in ("sbcr_out_of_limits", "packaged"):
            if r[k] not in BOOL:
                raise InputError(f"{where}: {k} {r[k]!r}")
            r[k] = BOOL[r[k]]
        cases[r["case"]] = r
    if len(cases) != expected_cases:
        raise InputError(f"{path} has {len(cases)} cases, and the frame of the coding at scale has {expected_cases}")
    _, sheet = read_csv(os.path.join(draw, "coding_sheet.csv"))
    packaged = {c for c, r in cases.items() if r["packaged"]}
    if {r["case"] for r in sheet} != packaged:
        raise InputError("the cases of the coding sheet are not the packaged cases of the sealed file")
    return record, cases


def load_run1(folder, case, step):
    path = os.path.join(folder, case, "run1.json")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise InputError(f"{case}: no run 1 of the {step} step in {folder}") from None
    rec = json.loads(text)
    if rec.get("step") != step or rec.get("case") != case or (rec.get("output") or {}).get("case") != case:
        raise InputError(f"{path}: not a record of the {step} step of {case}")
    return rec, text


def further_measured(row):
    s, m = float(row["sim_sbcr"]), float(row["sim_mergegen"])
    return "equal" if s == m else ("sbcr" if s < m else "mergegen")


def join(cases, draw, dims, scheme_sha, description, labeling):
    """One row per case of the bands, with the annotator's labels of the packaged ones."""
    single = len(dims) == 1
    rows = []
    for case in sorted(cases):
        r = cases[case]
        tool = {"A": r["candidate_a"], "B": r["candidate_b"]}
        row = {k: r[k] for k in SEALED_COLUMNS}
        row.update({"closer": "", "further_annotator": "", "further_measured": further_measured(r),
                    "empty_candidate_tool": ""})
        row.update({f"code_{d['id']}": "" for d in dims})
        if r["packaged"]:
            with open(os.path.join(draw, "packages", f"{case}.md"), encoding="utf-8") as fh:
                package = fh.read()
            p = parse_package(package, case)
            empty, _ = package_flags(p)
            if empty:
                row["empty_candidate_tool"] = tool["A"] if p["cand_a_state"] != "text" else tool["B"]
            desc, desc_text = load_run1(description, case, "description")
            label, _ = load_run1(labeling, case, "labeling")
            where = f"{case}, labeling run 1"
            if desc.get("package_sha256") != sha256_text(package) or label.get("package_sha256") != sha256_text(package):
                raise InputError(f"{case}: the description or the label was not written from {draw}/packages/{case}.md")
            if label.get("description_sha256") != sha256_text(desc_text):
                raise InputError(f"{where}: written from another description than {description}/{case}/run1.json")
            if label.get("scheme_sha256") != scheme_sha:
                raise InputError(f"{where}: labeled with another scheme than the one given")
            closer = desc["output"].get("closer")
            if closer not in ("A", "B", "equal", "unclear"):
                raise InputError(f"{case}, description run 1: closer {closer!r}")
            row["closer"] = closer
            row["further_annotator"] = tool["B" if closer == "A" else "A"] if closer in tool else closer
            for d in dims:
                row[f"code_{d['id']}"] = annotator_code(label["output"], d, single, where)
        rows.append(row)
    return rows


def load_block1(sheet, approval, dims, cases):
    """Every case of block 1, with the authors' consensus, the approval label and its case at scale, if any."""
    _, rows = read_csv(sheet)
    at_scale = {r["draw_case"]: c for c, r in cases.items() if r["draw_role"] == "sample" and r["draw_case"]}
    block1 = [r for r in rows if str(r.get("block", "")).strip() == "1"]
    if not block1:
        raise InputError(f"{sheet} has no case of block 1")
    approved, _ = load_annotator(approval, dims, [{"case": r["case"], "block": 1} for r in block1])
    out = []
    for r in block1:
        authors = {}
        for d in dims:
            code = (r.get(f"dominant_code_{d['id']}") or "").strip()
            if code and code not in d["codes"]:
                raise InputError(f"{sheet}, {r['case']}: dominant_code_{d['id']} {code!r} is not a code of the scheme")
            authors[d["id"]] = code
        out.append({"draw_case": r["case"], "case": at_scale.get(r["case"], ""), "authors": authors,
                    "approval": approved[r["case"]][1]})
    return out


def load_sample_sealed(path, cases):
    """Per case of the sample draw, the tool behind its candidates and its case at scale, if any."""
    if sha256_file(path) != SAMPLE_SEALED_SHA256:
        raise InputError(f"{path} does not have the SHA-256 of the sealed file of the sample draw")
    columns, rows = read_csv(path)
    missing = [c for c in SAMPLE_COLUMNS if c not in columns]
    if missing:
        raise InputError(f"{path}: columns missing: {missing}")
    at_scale = {r["draw_case"]: c for c, r in cases.items() if r["draw_case"]}
    return [{**{k: r[k] for k in SAMPLE_COLUMNS}, "case_at_scale": at_scale.get(r["case"], "")} for r in rows]


# --- measures ---------------------------------------------------------------------------

def frequencies(rows, dims):
    """Cases per code over all bands, per band, per band and dataset, per band and further tool."""
    out = []
    labeled = [r for r in rows if r["packaged"]]

    def add(cut, band, dataset, further, subset):
        for d in dims:
            counts = Counter(r[f"code_{d['id']}"] for r in subset)
            for c in d["categories"]:
                out.append({"cut": cut, "band": band, "dataset": dataset, "further": further, "dimension": d["id"],
                            "code": c["code"], "cases": counts[c["code"]], "of": len(subset)})

    add("all", "", "", "", labeled)
    for b in BANDS:
        in_band = [r for r in labeled if r["band"] == b]
        add("band", b, "", "", in_band)
        for ds in sorted({r["dataset"] for r in in_band}):
            add("band_dataset", b, ds, "", [r for r in in_band if r["dataset"] == ds])
        for f in FURTHER:
            add("band_further", b, "", f, [r for r in in_band if r["further_annotator"] == f])
    return out


def pair_measure(pairs):
    pairs = [(a, b) for a, b in pairs if a and b]
    return {"cases": len(pairs), "agreements": sum(a == b for a, b in pairs),
            "kappa": kappa(pairs) if pairs else None}


def block1_measures(block1, joined, dims):
    """Agreement over the cases of block 1 in the bands, and of the approval over all of block 1."""
    by_case = {r["case"]: r for r in joined}
    kept = [c for c in block1 if c["case"]]
    out = {}
    for d in dims:
        i = d["id"]
        scale = [by_case[c["case"]][f"code_{i}"] for c in kept]
        authors = [c["authors"][i] for c in kept]
        approval = [c["approval"][i] for c in kept]
        out[i] = {"scale_vs_authors": pair_measure(zip(scale, authors)),
                  "scale_vs_approval": pair_measure(zip(scale, approval)),
                  "approval_vs_authors": pair_measure(zip(approval, authors)),
                  "approval_vs_authors_all": pair_measure((c["approval"][i], c["authors"][i]) for c in block1)}
    return out


# --- report -----------------------------------------------------------------------------

def share(k, n):
    return f"{k} ({100 * k / n:.1f}%)" if n else f"{k}"


def fmt(x):
    return "n/a" if x is None else f"{x:.3f}"


def render(report, dims, freq):
    def cell(cut, band, further, dim, code):
        return next(f for f in freq if f["cut"] == cut and f["band"] == band and f["further"] == further
                    and f["dimension"] == dim and f["code"] == code)

    lines = ["# Join of the RQ4 labels at scale with band and tool", "",
             f"Generated {report['generated']} by `analysis/rq4/join_scale.py` at commit "
             f"`{report['git_commit']}`" + (", with local changes" if report["git_dirty"] else "") + ".", "",
             "## Inputs", ""]
    lines += [f"- {k}: `{v}`" for k, v in report["inputs"].items()]
    lines += ["", "The bands are labeled whole, so the shares below are those of the population of the bands in "
              "partition 1 and carry no sampling margin. The error left is the "
              "annotator's, measured by the per-category agreement of block 1.", "", "## Cases per band", "",
              "| band | conflicts | labeled | not labeled (package too large) | above SBCR's size limit |",
              "|---|---:|---:|---:|---:|"]
    for b in BANDS + ("all",):
        c = report["cases"][b]
        name = "**all bands**" if b == "all" else BAND_NAMES[b]
        lines.append(f"| {name} | {c['conflicts']} | {c['labeled']} | {c['not_labeled']} | {c['above_sbcr_limit']} |")
    for d in dims:
        lines += ["", f"## {d['name']} per band", "",
                  "| code | " + " | ".join(BAND_NAMES[b] for b in BANDS) + " | all bands |",
                  "|---|" + "---:|" * (len(BANDS) + 1)]
        for c in d["categories"]:
            cells = [cell("band", b, "", d["id"], c["code"]) for b in BANDS] + [cell("all", "", "", d["id"], c["code"])]
            lines.append(f"| {c['code']} · {c['name']} | " + " | ".join(share(x["cases"], x["of"]) for x in cells) + " |")
    lines.append("")
    for d in dims:
        lines += [f"## {d['name']} per band and tool of the further candidate", "",
                  "The further candidate as the annotator read it, from the field `closer` of its description.", ""]
        for b in BANDS:
            lines += [f"**{BAND_NAMES[b]}**", "", "| code | " + " | ".join(TOOL_NAMES[f] for f in FURTHER) + " |",
                      "|---|" + "---:|" * len(FURTHER)]
            for c in d["categories"]:
                cells = [cell("band_further", b, f, d["id"], c["code"]) for f in FURTHER]
                if any(x["cases"] for x in cells):
                    lines.append(f"| {c['code']} | " + " | ".join(share(x["cases"], x["of"]) for x in cells) + " |")
            lines.append("")
    lines += ["## Further candidate: the annotator's reading and the similarity", "",
              "Rows: the tool of the candidate the annotator read as further. Columns: the tool of the candidate "
              "with the lower similarity to the resolution, all whitespace removed. Packaged cases only.", ""]
    for b in BANDS:
        x = report["further"][b]
        lines += [f"**{BAND_NAMES[b]}**", "", "| annotator \\ similarity | SBCR | MergeGen | equal |",
                  "|---|---:|---:|---:|"]
        for f in FURTHER:
            lines.append(f"| {TOOL_NAMES[f]} | " + " | ".join(str(x[f][m]) for m in ("sbcr", "mergegen", "equal")) + " |")
        lines.append("")
    lines += ["## Empty candidates", "",
              "Packaged cases with one empty candidate and no empty version, per band "
              "and tool of the empty candidate, with the codes the annotator gave them.", "",
              "| band | tool | cases | above SBCR's size limit | candidate codes |", "|---|---|---:|---:|---|"]
    for e in report["empty_candidates"]:
        codes = ", ".join(f"{k} {v}" for k, v in sorted(e["codes"].items()))
        lines.append(f"| {BAND_NAMES[e['band']]} | {TOOL_NAMES[e['tool']]} | {e['cases']} | {e['above_sbcr_limit']} "
                     f"| {codes} |")
    b1 = report.get("block1")
    if b1:
        lines += ["", "## Block 1", "",
                  f"{b1['in_bands']} of the {b1['cases']} cases of block 1 are in the bands, and only they have a "
                  "label at scale. Agreement over the cases where both sides have a code. The first three pairs "
                  "are over the cases in the bands, so the pair of the approval and the authors is not the kappa of "
                  "the approval of the annotator, which the last pair gives over all of block 1.",
                  "", "| dimension | pair | cases | same code | kappa |", "|---|---|---:|---:|---:|"]
        for d in dims:
            for pair, name in (("scale_vs_authors", "scale, authors"), ("scale_vs_approval", "scale, approval"),
                               ("approval_vs_authors", "approval, authors"),
                               ("approval_vs_authors_all", "approval, authors, all of block 1")):
                m = b1["measures"][d["id"]][pair]
                lines.append(f"| {d['id']} | {name} | {m['cases']} | {m['agreements']} | {fmt(m['kappa'])} |")
        lines += ["", "Per case in `block1.csv`."]
    st = report.get("sample_tools")
    if st:
        lines += ["", "## Packages the authors read", "",
                  f"The tool behind the candidates of the {st['cases']} cases of the sample draw is in "
                  f"`sample_tools.csv`, in the bands or not. {st['at_scale']} of them are in the bands and have a "
                  "case at scale."]
    return "\n".join(lines) + "\n"


def main(argv=None, expected_cases=EXPECTED_CASES):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sealed", required=True)
    p.add_argument("--draw", required=True)
    p.add_argument("--scheme", required=True)
    p.add_argument("--description", required=True)
    p.add_argument("--labeling", required=True)
    p.add_argument("--sheet", help="coding sheet with the authors' consensus of block 1")
    p.add_argument("--approval", help="labeling folder of block 1, the run that approved the annotator")
    p.add_argument("--sample-sealed", help="sealed_sample.csv of the sample draw")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    sealed, draw, scheme, description, labeling, out = (
        os.path.expanduser(x) for x in (args.sealed, args.draw, args.scheme, args.description, args.labeling, args.out))
    sheet, approval, sample_sealed = (os.path.expanduser(x) if x else None
                                      for x in (args.sheet, args.approval, args.sample_sealed))
    if bool(sheet) != bool(approval):
        raise SystemExit("--sheet and --approval go together. Nothing was written")

    read = [draw, description, labeling] + ([approval, os.path.dirname(os.path.dirname(os.path.abspath(sheet)))]
                                            if sheet else [])
    if inside_git_work_tree(out):
        raise SystemExit(f"{out} is inside a Git work tree, and the join names the tool of each case. "
                         "Nothing was written")
    for folder in read:
        if inside(out, folder):
            raise SystemExit(f"{out} is inside {folder}, which the analysts or the annotator read. Nothing was written")
    if any(os.path.exists(os.path.join(out, n)) for n in OUTPUTS):
        raise SystemExit(f"{out} already holds a join. Nothing was written")

    try:
        version, dims = load_scheme(scheme)
        scheme_sha = sha256_file(scheme)
        if scheme_sha != SCHEME_SHA256:
            raise InputError(f"{scheme} is not the frozen scheme {SCHEME_SHA256}")
        draw_record, cases = load_sealed(sealed, draw, expected_cases)
        joined = join(cases, draw, dims, scheme_sha, description, labeling)
        block1 = None
        if sheet:
            block1 = load_block1(sheet, approval, dims, cases)
        sample_tools = load_sample_sealed(sample_sealed, cases) if sample_sealed else []
    except (InputError, PackageError) as e:
        raise SystemExit(f"{e}. Nothing was written")

    freq = frequencies(joined, dims)
    labeled = [r for r in joined if r["packaged"]]
    counts = {}
    for b in BANDS + ("all",):
        sub = [r for r in joined if b == "all" or r["band"] == b]
        counts[b] = {"conflicts": len(sub), "labeled": sum(r["packaged"] for r in sub),
                     "not_labeled": sum(not r["packaged"] for r in sub),
                     "above_sbcr_limit": sum(r["sbcr_out_of_limits"] for r in sub)}
    further = {b: {f: {m: sum(1 for r in labeled if r["band"] == b and r["further_annotator"] == f
                              and r["further_measured"] == m) for m in ("sbcr", "mergegen", "equal")}
                   for f in FURTHER} for b in BANDS}
    cand = next((d["id"] for d in dims if d["id"] == "cand"), dims[-1]["id"])
    empty = []
    for b in BANDS:
        for t in TOOLS:
            sub = [r for r in labeled if r["band"] == b and r["empty_candidate_tool"] == t]
            if sub:
                empty.append({"band": b, "tool": t, "cases": len(sub),
                              "above_sbcr_limit": sum(r["sbcr_out_of_limits"] for r in sub),
                              "codes": dict(Counter(r[f"code_{cand}"] for r in sub))})
    commit, dirty = git_state()
    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit, "git_dirty": dirty,
        "inputs": {"sealed_sha256": sha256_file(sealed), "coding_sheet_sha256": draw_record["coding_sheet_sha256"],
                   "scheme_version": version, "scheme_sha256": scheme_sha, "description": description,
                   "labeling": labeling, "script_sha256": sha256_file(__file__)},
        "cases": counts, "further": further, "empty_candidates": empty}
    block1_rows = []
    if sheet:
        report["inputs"]["sheet_sha256"] = sha256_file(sheet)
        report["inputs"]["approval"] = approval
        by_case = {r["case"]: r for r in joined}
        report["block1"] = {"cases": len(block1), "in_bands": sum(1 for c in block1 if c["case"]),
                            "measures": block1_measures(block1, joined, dims)}
        for c in (c for c in block1 if c["case"]):
            r = by_case[c["case"]]
            row = {"draw_case": c["draw_case"], "case": c["case"], "band": r["band"],
                   "further_measured": r["further_measured"], "further_annotator": r["further_annotator"]}
            for d in dims:
                row.update({f"authors_{d['id']}": c["authors"][d["id"]], f"approval_{d['id']}": c["approval"][d["id"]],
                            f"scale_{d['id']}": r[f"code_{d['id']}"]})
            block1_rows.append(row)
    if sample_sealed:
        report["inputs"]["sample_sealed_sha256"] = SAMPLE_SEALED_SHA256
        report["sample_tools"] = {"cases": len(sample_tools),
                                  "at_scale": sum(1 for r in sample_tools if r["case_at_scale"])}

    text = render(report, dims, freq)
    os.makedirs(out, exist_ok=True)
    columns = SEALED_COLUMNS + ["closer", "further_annotator", "further_measured", "empty_candidate_tool"] + \
        [f"code_{d['id']}" for d in dims]
    write_csv(os.path.join(out, "joined.csv"), columns, joined)
    write_csv(os.path.join(out, "frequencies.csv"),
              ["cut", "band", "dataset", "further", "dimension", "code", "cases", "of"], freq)
    b1_columns = ["draw_case", "case", "band", "further_measured", "further_annotator"] + \
        [f"{k}_{d['id']}" for d in dims for k in ("authors", "approval", "scale")]
    write_csv(os.path.join(out, "block1.csv"), b1_columns, block1_rows)
    write_csv(os.path.join(out, "sample_tools.csv"), SAMPLE_COLUMNS + ["case_at_scale"], sample_tools)
    with open(os.path.join(out, "join_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "join_report.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
