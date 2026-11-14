#!/usr/bin/env python3
"""Builds the package of each RQ4 case, the material the coders and the automatic annotator read.

Reads the sealed file of `draw_sample.py` (every drawn case, with the tool behind candidate A) and
writes, for each case of the sample and of the pilot:

- `<out>/packages/<case>.md`: chunk id, project, merge commit, file, constructs, the conflict, its
  base, the developer's resolution, candidates A and B, and the similarity between the resolution
  and each version and the parents. It says nothing about the band or about which tool produced
  each candidate;
- `<out>/index.md`: the cases in coding order, pilot first, then blocks 1 to 3;
- `<reveal>/<case>.md`: which tool produced each candidate. Nobody opens them during the coding:
  the tool and the band are joined to the labels afterwards, by script. They go by default to
  `reveal/` next to the sealed file, and the script refuses a folder inside `--out` or inside a
  Git work tree.

The similarity between each candidate and the resolution is not written where the coders read:
the difference between the two is `d`, which would give away the band. The script recomputes it
for each packaged candidate and stops if it differs from the sealed value. It also checks that
the sealed file is the one `draw.json` records and that its cases match `coding_sheet.csv`, and
refuses to write over an earlier run. Every check runs before anything is written.

A case above SBCR's size limit has no SBCR candidate, so the package shows an empty candidate, as
for an empty MergeGen candidate, which keeps the tool hidden; the reason goes to the reveal file.

Layout of the candidates. MergeGen reads the conflict with its whitespace collapsed, so its
candidate is one line, while SBCR keeps the layout of the lines it combines, and the layout alone
would name the tool. Both candidates are shown with their whitespace collapsed and laid out again
from `;`, `{`, `}`, block comments and the commas of literals (`layout`). The similarity ignores
whitespace, so nothing it measures is lost. Nothing marks where a `//` comment ended once the line
breaks are gone, and code written without `;` keeps several statements on one line; every package
carries the same note on this before the candidates (`LAYOUT_NOTE`). The conflict, the base and the
resolution keep their original layout.

Constructs: only Dataset1 records them (`kind_conflict`). The project is shown as `owner/repo`.
The similarities with the versions are `2*|LCS| / (len1 + len2)` on the text without spaces and
line breaks, and the similarity with the parents is their mean.

    python analysis/rq4/build_packages.py --root <root of partition 1> --sealed <sealed CSV> \
        --draw <folder of draw_sample.py> --data-root <data> --out <dir>
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "similarity"))
from sbcr_similarity import gestalt, without_spaces  # noqa: E402
ARM = "mg"
SBCR_SEED = "3022024"
LANGUAGE = {"dataset1": "java", "dataset2_Java": "java", "dataset2_CSharp": "csharp",
            "dataset2_JavaScript": "javascript", "dataset2_TypeScript": "typescript"}
NAMES = {"sbcr": "SBCR", "mergegen": "MergeGen"}
TOLERANCE = 1e-9
# what may follow a closing brace on the same line: `} else`, `}).then`
CONTINUES_AFTER_BRACE = re.compile(r"\s*(\.|(else|catch|finally|while)\b)")
# the same in every package, so it says nothing about the case or the tools
LAYOUT_NOTE = ("*Both candidates are shown with their whitespace collapsed and laid out again by the same "
               "rule, so their layout says nothing about the tool that produced them. Around a `//` comment "
               "the layout may mislead: the code that followed the comment may appear on its line, as if "
               "commented out, and the rest of the comment may appear on the lines below, as if it were "
               "code, with its braces shifting the indentation. In code written without `;`, one line may "
               "hold several statements. The conflict above shows the original layout.*")
BASE_HEADER = "Base version (common ancestor of versions 1 and 2)"
# how far a quote may be from the one that closes it before it is taken as a stray quote
LITERAL_REACH = 300
# what may precede a brace that opens an initializer or object literal, not a block
OPENS_LITERAL = re.compile(r"([=(,:\[\]?]|\breturn)\s*$")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_metadata(data_root, dataset):
    """Project, merge commit, file and constructs per chunk id, as the original datasets record them."""
    if dataset == "dataset1":
        m = pd.read_csv(os.path.join(data_root, "dataset1_metadata.csv"), dtype={"chunk_id": str})
        m = m.rename(columns={"sha": "commit", "path": "file", "kind_conflict": "constructs"})
        # Dataset1 prefixes the path with the project; Dataset2 keeps it relative to the repository
        m["file"] = [f[len(p) + 1:] if str(f).lower().startswith(str(p).lower() + "/") else f
                     for f, p in zip(m.file.astype(str), m.project.astype(str))]
    else:
        m = pd.DataFrame(load_json(os.path.join(data_root, f"{dataset}_metadata.json")))
        m["chunk_id"] = m.chunk_id.astype(str)
        m = m.rename(columns={"repo": "project", "commitHash": "commit", "fileName": "file"})
        # Dataset2 records the GitHub URL; Dataset1 records owner/repo
        m["project"] = m.project.astype(str).str.replace(r"^https://github\.com/", "", regex=True)
        m["constructs"] = None
    return m.drop_duplicates("chunk_id").set_index("chunk_id")[["project", "commit", "file", "constructs"]]


def load_content(root, dataset):
    d = load_json(os.path.join(root, "data", f"{dataset}.json"))
    ids = [str(c) for c in d["chunk_id"]]
    return {c: {"v1": a, "v2": b, "base": o, "resolution": r}
            for c, a, b, o, r in zip(ids, d["all_raw_a"], d["all_raw_b"], d["all_raw_base"], d["all_raw_res"])}


def load_candidates(root, dataset):
    mergegen = load_json(os.path.join(root, "mergeGen", "JIT", f"{dataset}_{ARM}",
                                      f"model_{dataset}_{ARM}", "candidates.json"))
    sbcr_dir = os.path.join(root, "sbcr", f"eval_{dataset}_{ARM}_s{SBCR_SEED}", "OUTPUT")
    return {str(k): v for k, v in mergegen.items()}, sbcr_dir


def read_sbcr(sbcr_dir, chunk_id):
    # same reading as sbcr_similarity.py, so that the recomputed similarity matches
    with open(os.path.join(sbcr_dir, chunk_id), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def sim(a, b):
    return gestalt(without_spaces(a), without_spaces(b))


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def inside_git_work_tree(path):
    path = os.path.abspath(path)  # a relative path would climb to "" and never stop
    while not os.path.isdir(path):  # the folder may not exist yet; ask about its nearest ancestor
        path = os.path.dirname(path)
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # different drives on Windows
        return False


def has_files(path):
    return os.path.isfile(path) or (os.path.isdir(path) and bool(os.listdir(path)))


def check_draw(sealed, cases, draw):
    """Stops unless the sealed file is the one recorded by the draw whose sheet the analysts use."""
    record = load_json(os.path.join(draw, "draw.json"))
    if sha256(sealed) != record["sealed_sha256"]:
        raise SystemExit(f"{sealed} is not the sealed file recorded in {draw}/draw.json; nothing was written")
    sheet = pd.read_csv(os.path.join(draw, "coding_sheet.csv"), dtype={"chunk_id": str})
    key = ["case", "dataset", "chunk_id"]
    if set(map(tuple, sheet[key].to_numpy())) != set(map(tuple, cases[key].to_numpy())):
        raise SystemExit(f"the cases of {sealed} differ from {draw}/coding_sheet.csv; nothing was written")
    return record


def body(text):
    """The text without the newline that ends its last line, so the fence adds no blank line."""
    text = str(text)
    return text[:-1] if text.endswith("\n") else text


def fenced(text, language):
    """A code block whose fence is longer than any backtick run inside the text."""
    text = str(text)
    if not text:
        return "*(empty)*"
    if not text.strip():
        return "*(whitespace only)*"
    longest, run = 0, 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{body(text)}\n{fence}"


def closing_quote(text, i):
    """Index of the quote that closes the literal opened at `i`, or -1 if none is near.

    Candidates are fragments, so a quote may never close; treating it as a literal would
    swallow every line break after it.
    """
    j, end = i + 1, min(len(text), i + 1 + LITERAL_REACH)
    while j < end:
        if text[j] == "\\":
            j += 2
        elif text[j] == text[i]:
            return j
        else:
            j += 1
    return -1


def layout(text):
    """One layout for both candidates, so that it does not tell which tool produced each.

    Collapses the whitespace, as MergeGen's input is, then breaks the line after `;` (except
    inside a `for` header), after `{`, before and after `}`, and after `,` between the
    braces of an initializer or object literal (a brace after `=`, `(`, `,`, `:`, `[`, `]`,
    `?` or `return`), indenting by brace depth. `} else`, `} catch`, `} finally`, `} while`
    and `}).then` stay on one line. A block comment gets lines of its own, split where its
    ` * ` continuation lines were. Nothing breaks inside a string or character literal. A `//` comment cannot be told apart from the code after
    it once the whitespace is collapsed; inside it, quotes are ignored and the breaks apply.
    """
    text = " ".join(str(text).split())
    lines, line = [], ""
    # per brace level: open parentheses, where a `for (` opened, and whether the braces hold
    # an initializer or object literal, whose commas break the line
    parens, for_at, literal = [0], [None], [False]
    comment = False

    def flush():
        nonlocal line
        if line.strip():
            lines.append("    " * (len(parens) - 1) + line.strip())
        line = ""

    i = 0
    while i < len(text):
        ch = text[i]
        end = text.find("*/", i + 2) if text.startswith("/*", i) else -1
        if end >= 0:  # an unclosed `/*` is a fragment, laid out as code
            flush()
            for part in re.split(r" (?=\*(?: |/|$))", text[i:end + 2]):
                line = part
                flush()
            i = end + 2
            continue
        if text.startswith("//", i):
            comment = True
        elif ch in "\"'`" and not comment:
            end = closing_quote(text, i)
            if end >= 0:
                line += text[i:end + 1]
                i = end + 1
                continue
        line += ch
        if ch == "(":
            if for_at[-1] is None and re.search(r"\bfor\s*\($", line):
                for_at[-1] = parens[-1]
            parens[-1] += 1
        elif ch == ")":
            parens[-1] = max(0, parens[-1] - 1)
            if for_at[-1] is not None and parens[-1] <= for_at[-1]:
                for_at[-1] = None
        elif ch == ";" and for_at[-1] is None:
            flush()
            comment = False
        elif ch == "," and parens[-1] == 0 and literal[-1]:
            flush()
        elif ch == "{":
            literal.append(bool(OPENS_LITERAL.search(line[:-1])))
            flush()
            parens.append(0)
            for_at.append(None)
            comment = False
        elif ch == "}":
            line = line[:-1]
            flush()
            if len(parens) > 1:
                parens.pop()
                for_at.pop()
                literal.pop()
            line = "}"
            while i + 1 < len(text) and text[i + 1] in ",)":
                if text[i + 1] == ")":
                    parens[-1] = max(0, parens[-1] - 1)
                line += text[i + 1]
                i += 1
            if text[i + 1:i + 2] == ";":
                line += ";"
                i += 1
            if not CONTINUES_AFTER_BRACE.match(text, i + 1):
                flush()
            comment = False
        i += 1
    flush()
    return "\n".join(lines)


def conflict(v1, v2):
    """The conflict with its markers; an empty side is labeled on its marker, not shown as a blank line."""
    v1, v2 = str(v1), str(v2)
    lines = (["<<<<<<< version 1" + ("" if v1 else " (empty)")] + ([body(v1)] if v1 else [])
             + ["======="]
             + ([body(v2)] if v2 else []) + [">>>>>>> version 2" + ("" if v2 else " (empty)")])
    return "\n".join(lines)


def package(case, meta, content, cand_a, cand_b, language, sims):
    constructs = meta["constructs"] if isinstance(meta["constructs"], str) and meta["constructs"] \
        else "not available (only Dataset1 records the constructs of a chunk)"
    return "\n".join([
        f"# Case {case.case}",
        "",
        f"- **Dataset:** {case.dataset}",
        f"- **Chunk id:** {case.chunk_id}",
        f"- **Project:** {meta['project']}",
        f"- **Merge commit:** {meta['commit']}",
        f"- **File:** {meta['file']}",
        f"- **Constructs:** {constructs}",
        "",
        "## Similarity of the developers' resolution",
        "",
        "| with | similarity |",
        "|---|---:|",
        f"| version 1 | {sims['v1']:.3f} |",
        f"| version 2 | {sims['v2']:.3f} |",
        f"| parents (mean of the two) | {sims['parents']:.3f} |",
        "",
        "## Conflict",
        "",
        fenced(conflict(content["v1"], content["v2"]), language),
        "",
        f"## {BASE_HEADER}",
        "",
        fenced(content["base"], language),
        "",
        "## Developers' resolution",
        "",
        fenced(content["resolution"], language),
        "",
        LAYOUT_NOTE,
        "",
        "## Candidate A",
        "",
        fenced(layout(cand_a), language),
        "",
        "## Candidate B",
        "",
        fenced(layout(cand_b), language),
        "",
    ])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="root of partition 1")
    p.add_argument("--sealed", required=True, help="sealed CSV written by draw_sample.py")
    p.add_argument("--draw", required=True, help="folder where draw_sample.py wrote draw.json and coding_sheet.csv")
    p.add_argument("--data-root", required=True, help="folder with the original datasets and their metadata")
    p.add_argument("--out", required=True, help="directory where packages/ and index.md go")
    p.add_argument("--reveal", help="directory for the reveal files, outside --out and outside any Git "
                                    "work tree (default: reveal/ next to the sealed file)")
    args = p.parse_args()
    root, sealed, draw, data_root, out = (os.path.expanduser(x) for x in
                                          (args.root, args.sealed, args.draw, args.data_root, args.out))
    reveal = os.path.expanduser(args.reveal) if args.reveal else os.path.join(os.path.dirname(os.path.abspath(sealed)), "reveal")

    if inside(reveal, out):
        raise SystemExit(f"{reveal} is inside --out, which the analysts and the annotator read; nothing was written")
    if inside_git_work_tree(reveal):
        raise SystemExit(f"{reveal} is inside a Git work tree; put the reveal files elsewhere. Nothing was written")
    stale = [x for x in (os.path.join(out, "packages"), os.path.join(out, "index.md"),
                         os.path.join(out, "reveal"), reveal) if has_files(x)]
    if stale:
        raise SystemExit(f"output from an earlier run is in the way: {stale}; remove it first. Nothing was written")

    cases = pd.read_csv(sealed, dtype={"chunk_id": str}).sort_values(["block", "position"])
    if "sbcr_out_of_limits" not in cases.columns:
        raise SystemExit(f"{sealed} has no sbcr_out_of_limits column. Nothing was written")
    record = check_draw(sealed, cases, draw)

    # everything is built and checked in memory first, so that a mismatch writes nothing
    mismatches, packages, reveals = [], {}, {}
    for dataset, group in cases.groupby("dataset", sort=False):
        meta = load_metadata(data_root, dataset)
        content = load_content(root, dataset)
        mergegen, sbcr_dir = load_candidates(root, dataset)
        for case in group.itertuples():
            out_of_limits = bool(case.sbcr_out_of_limits)
            c = content[case.chunk_id]
            if out_of_limits:
                # no SBCR candidate: shown empty, and the sealed score must be 0
                candidate = {"sbcr": "", "mergegen": mergegen[case.chunk_id]}
                if case.sim_sbcr != 0 or os.path.exists(os.path.join(sbcr_dir, case.chunk_id)):
                    mismatches.append({"case": case.case, "tool": "sbcr (out of limits)"})
                checks = (("mergegen", case.sim_mergegen),)
            else:
                candidate = {"sbcr": read_sbcr(sbcr_dir, case.chunk_id), "mergegen": mergegen[case.chunk_id]}
                checks = (("sbcr", case.sim_sbcr), ("mergegen", case.sim_mergegen))
            for tool, expected in checks:
                got = sim(candidate[tool], c["resolution"])
                if abs(got - expected) > TOLERANCE:
                    mismatches.append({"case": case.case, "tool": tool})
            s1, s2 = sim(c["v1"], c["resolution"]), sim(c["v2"], c["resolution"])
            sims = {"v1": s1, "v2": s2, "parents": (s1 + s2) / 2}
            packages[case.case] = package(case, meta.loc[case.chunk_id], c, candidate[case.candidate_a],
                                          candidate[case.candidate_b], LANGUAGE[dataset], sims)
            reveals[case.case] = (f"# Case {case.case}\n\n- **Candidate A:** {NAMES[case.candidate_a]}\n"
                                  f"- **Candidate B:** {NAMES[case.candidate_b]}\n"
                                  + ("\nSBCR produced no candidate: a version of the conflict has 20,000 "
                                     "characters or more, SBCR's size limit, and it scores 0.\n" if out_of_limits else ""))

    if mismatches:
        raise SystemExit(f"{len(mismatches)} packaged candidates do not match the sealed similarity "
                         f"(first ones: {mismatches[:5]}); check --root against the root used by the draw, "
                         f"{record.get('root')}. Nothing was written")

    lines = ["# RQ4 cases in coding order", "",
             "Which tool produced each candidate is not shown during the coding.", ""]
    for block, g in cases.groupby("block", sort=True):
        lines += ["## Pilot" if block == 0 else f"## Block {block}", ""]
        lines += [f"- [{c}](packages/{c}.md)" for c in g.case]
        lines.append("")

    os.makedirs(os.path.join(out, "packages"), exist_ok=True)
    os.makedirs(reveal, exist_ok=True)
    for case, text in packages.items():
        with open(os.path.join(out, "packages", f"{case}.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(os.path.join(reveal, f"{case}.md"), "w", encoding="utf-8") as fh:
            fh.write(reveals[case])
    with open(os.path.join(out, "index.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    counts = cases.role.value_counts().to_dict()
    print(f"packages: {len(cases)} ({counts}); candidates match the sealed similarities")
    print(f"cases out of SBCR's size limit, shown with an empty SBCR candidate: {int(cases.sbcr_out_of_limits.sum())}")
    print(f"written to {out}/packages and {out}/index.md; reveal files in {reveal}")


if __name__ == "__main__":
    main()
