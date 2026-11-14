#!/usr/bin/env python3
"""Reads the RQ4 packages and checks a coding scheme.

A library of `run_annotator.py`, `kappa_report.py` and `join_scale.py`. `parse_package` reads a
package written by `build_packages.py` back into its fields (case, metadata, similarities,
conflict split into its two versions, base, resolution and the two candidates). `check_scheme`
lists the problems of a frozen scheme. `check_draw_folder` refuses a folder that holds the sealed
files next to the packages.
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIM_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
# what must never sit next to the packages
SEALED_NAMES = ("sealed_sample.csv", "sealed_scale.csv", "reveal", "mergegen_ceiling.csv", "mergegen_ceiling.json",
                "population_tokens.csv", "candidates.json")
FIELDS = {"Dataset": "dataset", "Chunk id": "chunk_id", "Project": "project",
          "Merge commit": "commit", "File": "file", "Constructs": "constructs"}
SIM_ROWS = {"version 1": "v1", "version 2": "v2", "parents (mean of the two)": "parents"}
BASE = "Base version (common ancestor of versions 1 and 2)"  # BASE_HEADER of build_packages.py
SECTIONS = ("Similarity of the developers' resolution", "Conflict", BASE, "Developers' resolution",
            "Candidate A", "Candidate B")
FENCE = re.compile(r"^(`{3,})([\w#+-]*)$")
MARK_V1, MARK_SEP, MARK_V2 = "<<<<<<< version 1", "=======", ">>>>>>> version 2"


class PackageError(Exception):
    pass


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sections(text):
    """The package split at its `## ` headers: {header: body}, plus the part before the first.

    A `## ` line inside a code block is code (a Markdown string, a comment), not a header.
    `fenced` in build_packages.py makes the fence longer than any backtick run in the code, so
    the block ends only at a line that is its fence alone.
    """
    parts, name, lines, fence = {}, "", [], None
    for line in text.split("\n"):
        if fence is None and line.startswith("## "):
            parts[name] = "\n".join(lines)
            name, lines = line[3:].strip(), []
            continue
        if fence is None:
            m = FENCE.match(line)
            fence = m.group(1) if m else None
        elif line == fence:
            fence = None
        lines.append(line)
    parts[name] = "\n".join(lines)
    return parts


def block(body, where):
    """The content of the single code block in a section, as `fenced` in build_packages.py wrote it.

    Returns (text, state), with state `text`, `empty` or `whitespace`. The block's text is the
    original without the newline that ended its last line.
    """
    lines = body.strip("\n").split("\n")
    first = lines[0].strip() if lines else ""
    if first == "*(empty)*":
        return "", "empty"
    if first == "*(whitespace only)*":
        return "", "whitespace"
    m = FENCE.match(lines[0]) if lines else None
    if not m:
        raise PackageError(f"{where}: no code block")
    fence = m.group(1)
    try:
        end = lines.index(fence, 1)
    except ValueError:
        raise PackageError(f"{where}: code block not closed") from None
    return "\n".join(lines[1:end]), "text"


def after_block(body):
    """What follows the code block of a section (the layout note follows the resolution)."""
    lines = body.strip("\n").split("\n")
    m = FENCE.match(lines[0]) if lines else None
    if not m:
        return "\n".join(lines[1:]).strip()
    end = lines.index(m.group(1), 1)
    return "\n".join(lines[end + 1:]).strip()


def gestalt_3(a, b):
    """The package's similarity, to three decimals, as build_packages.py computes it."""
    sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
    from sbcr_similarity import gestalt, without_spaces  # noqa: E402  (needs pylcs)
    return f"{gestalt(without_spaces(a), without_spaces(b)):.3f}"


def split_conflict(conflict, resolution, sims, where):
    """The two versions of the conflict block, or None when the split cannot be told."""
    lines = conflict.split("\n")
    if len(lines) < 3 or not lines[0].startswith(MARK_V1) or not lines[-1].startswith(MARK_V2):
        raise PackageError(f"{where}: conflict markers not found")
    empty1, empty2 = lines[0].endswith("(empty)"), lines[-1].endswith("(empty)")
    inner = lines[1:-1]
    seps = [i for i, line in enumerate(inner) if line == MARK_SEP]
    if not seps:
        raise PackageError(f"{where}: conflict separator not found")

    def at(i):
        return "\n".join(inner[:i]), "\n".join(inner[i + 1:])

    # an empty version has no line at all, so its side of the separator must be empty
    fits = [i for i in seps if (i == 0) == empty1 and (i == len(inner) - 1) == empty2]
    if len(fits) == 1:
        return at(fits[0]) + ("single",)
    matching = [i for i in fits
                if (gestalt_3(at(i)[0], resolution), gestalt_3(at(i)[1], resolution)) == (sims["v1"], sims["v2"])]
    if len(matching) == 1:
        return at(matching[0]) + ("similarity",)
    return None


def parse_package(text, where="package"):
    parts = sections(text)
    missing = [s for s in SECTIONS if s not in parts]
    if missing:
        raise PackageError(f"{where}: sections missing: {missing}")
    head = parts[""]
    m = re.search(r"^# Case (\S+)$", head, re.M)
    if not m:
        raise PackageError(f"{where}: no case title")
    case = {"case": m.group(1)}
    for label, key in FIELDS.items():
        f = re.search(rf"^- \*\*{re.escape(label)}:\*\* (.*)$", head, re.M)
        if not f:
            raise PackageError(f"{where}: field {label!r} missing")
        case[key] = f.group(1)
    sims = {}
    for row in parts[SECTIONS[0]].split("\n"):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] in SIM_ROWS:
            sims[SIM_ROWS[cells[0]]] = cells[1]
    if set(sims) != set(SIM_ROWS.values()):
        raise PackageError(f"{where}: similarity table incomplete")
    case["sims"] = sims

    conflict, _ = block(parts["Conflict"], f"{where}, conflict")
    case["base"], case["base_state"] = block(parts[BASE], f"{where}, base")
    resolution, case["resolution_state"] = block(parts["Developers' resolution"], f"{where}, resolution")
    case["layout_note"] = after_block(parts["Developers' resolution"])
    if not case["layout_note"]:
        raise PackageError(f"{where}: layout note missing")
    case["conflict"], case["resolution"] = conflict, resolution
    split = split_conflict(conflict, resolution, sims, where)
    if split:
        case["v1"], case["v2"], case["split"] = split
    else:
        case["v1"] = case["v2"] = None
        case["split"] = "ambiguous"
    for side in ("A", "B"):
        text_, state = block(parts[f"Candidate {side}"], f"{where}, candidate {side}")
        case[f"cand_{side.lower()}"], case[f"cand_{side.lower()}_state"] = text_, state
    lang = FENCE.match(parts["Conflict"].strip("\n").split("\n")[0])
    case["language"] = lang.group(2) if lang else ""
    return case


def check_draw_folder(draw):
    found = [n for n in SEALED_NAMES if os.path.exists(os.path.join(draw, n))]
    if found:
        raise SystemExit(f"{draw} holds {found}, which the coders must not read; build from a folder "
                         "with only the packages and the coding sheet. Nothing was written")


def inside_git_work_tree(path):
    path = os.path.abspath(path)
    while not os.path.isdir(path):
        path = os.path.dirname(path)
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def check_scheme(scheme):
    """The problems of a frozen scheme: one or two dimensions, each with its categories and one residual."""
    if not isinstance(scheme, dict) or not isinstance(scheme.get("dimensions"), list):
        return ["the scheme is not an object with a list of dimensions"]
    dims = scheme["dimensions"]
    problems = [] if len(dims) in (1, 2) else [f"{len(dims)} dimensions, not 1 or 2"]
    ids = [d.get("id") if isinstance(d, dict) else None for d in dims]
    if len(set(ids)) != len(ids):
        problems.append("two dimensions with the same id")
    for k, d in enumerate(dims):
        where = f"dimension {k + 1}"
        if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not DIM_ID.match(d["id"]):
            problems.append(f"{where}: the id must match {DIM_ID.pattern}")
            continue
        where = f"dimension {d['id']}"
        if not isinstance(d.get("name"), str) or not d["name"].strip():
            problems.append(f"{where}: no name")
        # the rules of the dimension (order of the categories, criterion), read by the authors and the annotator alike
        if "rules" in d and (not isinstance(d["rules"], str) or not d["rules"].strip()):
            problems.append(f"{where}: rules, when given, must be a text")
        cats = d.get("categories")
        if not isinstance(cats, list) or not cats:
            problems.append(f"{where}: no categories")
            continue
        codes = [c.get("code") if isinstance(c, dict) else None for c in cats]
        if len(set(codes)) != len(codes):
            problems.append(f"{where}: two categories with the same code")
        for c in cats:
            if not isinstance(c, dict) or not isinstance(c.get("code"), str) or not CODE.match(c["code"]):
                problems.append(f"{where}: a code must match {CODE.pattern}")
                continue
            for field in ("name", "definition"):
                if not isinstance(c.get(field), str) or not c[field].strip():
                    problems.append(f"{where}, {c['code']}: no {field}")
            for flag in ("predefined", "residual"):
                if not isinstance(c.get(flag, False), bool):
                    problems.append(f"{where}, {c['code']}: {flag} must be true or false")
            if c.get("predefined") and c.get("residual"):
                problems.append(f"{where}, {c['code']}: a predefined value is not the residual category")
        # material that fits no category receives the residual category
        residual = sum(1 for c in cats if isinstance(c, dict) and c.get("residual") is True)
        if residual != 1:
            problems.append(f"{where}: {residual} residual categories, not 1")
    return problems
