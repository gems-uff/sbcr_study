#!/usr/bin/env python3
"""Builds the frame of the RQ4 coding at scale: every conflict of the three bands, blinded and packaged.

The automatic annotator labels every conflict of the three bands of partition 1, and the
frequencies per band come from its labels. The frame is that of `draw_sample.py`, with `d` on
`sim_lcs_no_whitespace` and the bands assigned per dataset by its `assign_bands`; band totals other
than `EXPECTED_BANDS` stop the script, as a different frame size does. Every conflict of the bands
is a case, whether or not the sample drew it, with a new identifier, package and order of the
candidates.

A conflict whose package would hold more than `MAX_PACKAGE_CHARS` characters gets an identifier
and a line in the sealed file, marked `packaged` false, and no package, reveal file or line of the
coding sheet: the annotator does not label it.

Blinding. Each case gets an identifier `S0001` to `S1985` from a drawn permutation of the frame,
and the order of the two candidates is drawn per case, both with the seed below. The package is
built by the functions of `build_packages.py`, so the annotator reads at scale the same material
as on the sample.

Outputs:
- `--sealed` (a file outside any Git work tree): per case, the dataset and chunk id, the band, `d`,
  the two similarities, the tool behind candidates A and B, whether the conflict is above SBCR's
  size limit, whether it was packaged, and its case and role in the sample draw, if any.
  `join_scale.py` reads it by script once the labeling ends;
- `--reveal` (by default `reveal/` beside the sealed file): the tool behind A and B, per case;
- `--out`, the folder the annotator reads: `packages/<case>.md`, `coding_sheet.csv` (case, role
  `scale`, position, dataset, chunk id, seed and date), `bands.csv` and `draw.json` (seed, date,
  script hash and commit, SHA-256 of the sealed file, of the coding sheet and of the list of
  packages, frame sizes, band counts, thresholds and checks).

Checks, all before anything is written: the frame sizes and the band totals; each packaged
candidate's similarity against the frame; and, with `--sample-draw`, each case the sample also
holds is packaged again under its old identifier and compared with the package of the sample, in
either order of the candidates. The script prints counts only, never a case with its band, `d` or
tool.

    python analysis/rq4/build_scale.py --root <root of partition 1> --data-root <data> \
        --sample-draw <folder of the sample> --out <dir> --sealed <file outside Git>
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
from build_packages import (LANGUAGE, NAMES, TOLERANCE, has_files, inside, load_candidates,  # noqa: E402
                            load_content, load_metadata, package, read_sbcr, sim)
from draw_sample import (BANDS, DATASETS, EXPECTED_FRAME, assign_bands, build_frame, git_state,  # noqa: E402
                         inside_git_work_tree)
from sbcr_scores import SIM  # noqa: E402
from sbcr_similarity import gestalt, normalize  # noqa: E402

# Drawn with `secrets.randbelow` before the script ran on the data.
SEED = 68461812

ROLE = "scale"
# A package is the two versions, the base, the resolution and the two candidates, plus a few hundred
# characters. Above this size it would take some 400 thousand tokens or more (about 2.5 characters
# per token), up to more than the 1 million of the model's context. The 6 conflicts of the bands
# above it have versions of 1 to 3 million characters, and the next largest package has under 100
# thousand.
MAX_PACKAGE_CHARS = 1_000_000
EXPECTED_BANDS = {"sbcr": 183, "mergegen": 692, "tie": 1110}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


def packages_sha256(texts):
    """SHA-256 of the list `<sha256>  <case>.md`, one line per package in the order of the cases.

    The runner of the coding at scale recomputes it from the files, so a package changed after
    this script ran is caught before any call.
    """
    lines = "".join(f"{sha256_bytes(texts[c].encode('utf-8'))}  {c}.md\n" for c in sorted(texts))
    return sha256_bytes(lines.encode("utf-8"))


def sim_frame(a, b):
    """The similarity of the frame, all whitespace removed."""
    return gestalt(normalize(a), normalize(b))


def bands_table(f, sizes, test_size):
    rows = []
    for ds in DATASETS:
        for band in BANDS:
            n = int(((f.dataset == ds) & (f.band == band)).sum())
            rows.append({"dataset": ds, "band": band, "conflicts": n,
                         "share_of_frame": n / sizes[ds] if sizes[ds] else 0.0,
                         "share_of_test": n / test_size[ds] if test_size[ds] else 0.0})
    return pd.DataFrame(rows)


def blind(f, rng):
    """Case identifiers from a drawn permutation, and the tool behind A drawn per case."""
    f = f.assign(dataset=pd.Categorical(f.dataset, DATASETS, ordered=True))
    f = f.sort_values(["dataset", "chunk_id"]).reset_index(drop=True)
    f["dataset"] = f.dataset.astype(str)
    f = f.iloc[rng.permutation(len(f))].reset_index(drop=True)
    f["position"] = np.arange(1, len(f) + 1)
    width = max(4, len(str(len(f))))
    f["case"] = [f"S{p:0{width}d}" for p in f.position]
    f["candidate_a"] = np.where(rng.integers(2, size=len(f)) == 0, "sbcr", "mergegen")
    f["candidate_b"] = np.where(f.candidate_a == "sbcr", "mergegen", "sbcr")
    return f


def build(cases, root, data_root, sample_packages=None):
    """Packages and reveal files in memory, the checks of the candidates, the reproduced packages, and
    the cases left out because their package would be larger than `MAX_PACKAGE_CHARS`."""
    mismatches, packages, reveals, too_large = [], {}, {}, []
    reproduced, not_reproduced = 0, []
    for dataset, group in cases.groupby("dataset", sort=False):
        meta = load_metadata(data_root, dataset)
        content = load_content(root, dataset)
        mergegen, sbcr_dir = load_candidates(root, dataset)
        for case in group.itertuples():
            out_of_limits = bool(case.sbcr_out_of_limits)
            c = content[case.chunk_id]
            if out_of_limits:
                candidate = {"sbcr": "", "mergegen": mergegen[case.chunk_id]}
                if case.sim_sbcr != 0 or os.path.exists(os.path.join(sbcr_dir, case.chunk_id)):
                    mismatches.append({"case": case.case, "tool": "sbcr (out of limits)"})
                checks = (("mergegen", case.sim_mergegen),)
            else:
                candidate = {"sbcr": read_sbcr(sbcr_dir, case.chunk_id), "mergegen": mergegen[case.chunk_id]}
                checks = (("sbcr", case.sim_sbcr), ("mergegen", case.sim_mergegen))
            size = sum(len(str(x)) for x in (c["v1"], c["v2"], c["base"], c["resolution"], *candidate.values()))
            if size > MAX_PACKAGE_CHARS:
                # no package, no check: the LCS of texts this long does not fit in memory
                too_large.append(case.case)
                continue
            for tool, expected in checks:
                if abs(sim_frame(candidate[tool], c["resolution"]) - expected) > TOLERANCE:
                    mismatches.append({"case": case.case, "tool": tool})
            s1, s2 = sim(c["v1"], c["resolution"]), sim(c["v2"], c["resolution"])
            sims = {"v1": s1, "v2": s2, "parents": (s1 + s2) / 2}
            m = meta.loc[case.chunk_id]
            packages[case.case] = package(case, m, c, candidate[case.candidate_a], candidate[case.candidate_b],
                                          LANGUAGE[dataset], sims)
            reveals[case.case] = (f"# Case {case.case}\n\n- **Candidate A:** {NAMES[case.candidate_a]}\n"
                                  f"- **Candidate B:** {NAMES[case.candidate_b]}\n"
                                  + ("\nSBCR produced no candidate: a version of the conflict has 20,000 "
                                     "characters or more, SBCR's size limit, and it scores 0.\n"
                                     if out_of_limits else ""))
            if sample_packages is not None and isinstance(case.draw_case, str):
                # the package of the sample, built again under its old identifier, in both orders
                old = case._replace(case=case.draw_case)
                with open(os.path.join(sample_packages, f"{case.draw_case}.md"), encoding="utf-8") as fh:
                    text = fh.read()
                if text in (package(old, m, c, candidate["sbcr"], candidate["mergegen"], LANGUAGE[dataset], sims),
                            package(old, m, c, candidate["mergegen"], candidate["sbcr"], LANGUAGE[dataset], sims)):
                    reproduced += 1
                else:
                    not_reproduced.append(case.draw_case)
    return mismatches, packages, reveals, too_large, reproduced, not_reproduced


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="root of partition 1")
    p.add_argument("--data-root", required=True, help="folder with the original datasets and their metadata")
    p.add_argument("--out", required=True, help="folder the annotator reads: packages/, coding_sheet.csv, "
                                                "bands.csv and draw.json")
    p.add_argument("--sealed", required=True, help="path of the sealed CSV, outside any Git work tree")
    p.add_argument("--reveal", help="folder for the reveal files, outside --out and outside any Git work tree "
                                    "(default: reveal/ next to the sealed file)")
    p.add_argument("--sample-draw", help="folder of the sample draw (coding_sheet.csv and packages/), "
                                         "to mark its cases and check that their packages are reproduced")
    p.add_argument("--allow-dirty", action="store_true",
                   help="run even if tracked files differ from the checked-out commit")
    args = p.parse_args()
    root, data_root, out, sealed = (os.path.expanduser(x) for x in (args.root, args.data_root, args.out, args.sealed))
    reveal = (os.path.expanduser(args.reveal) if args.reveal
              else os.path.join(os.path.dirname(os.path.abspath(sealed)), "reveal"))
    sample_draw = os.path.expanduser(args.sample_draw) if args.sample_draw else None

    commit, dirty = git_state()
    if dirty and not args.allow_dirty:
        raise SystemExit("tracked files differ from the checked-out commit; commit them first, "
                         "so that draw.json points to the code that built the frame")
    sealed_dir = os.path.dirname(os.path.abspath(sealed))
    for path, what in ((sealed_dir, "the sealed file"), (reveal, "the reveal files")):
        if inside_git_work_tree(path):
            raise SystemExit(f"{path} is inside a Git work tree; put {what} elsewhere. Nothing was written")
        if inside(path, out):
            raise SystemExit(f"{path} is inside --out, which the annotator reads; put {what} elsewhere. "
                             "Nothing was written")
    stale = [x for x in (os.path.join(out, "packages"), os.path.join(out, "coding_sheet.csv"),
                         os.path.join(out, "draw.json"), sealed, reveal) if has_files(x)]
    if stale:
        raise SystemExit(f"output from an earlier run is in the way: {stale}; remove it first. Nothing was written")

    f, test_size = build_frame(root, column=SIM)
    sizes = {ds: int(n) for ds, n in f.groupby("dataset").size().reindex(DATASETS, fill_value=0).items()}
    if sizes != EXPECTED_FRAME:
        raise SystemExit(f"frame differs from EXPECTED_FRAME: {sizes}, expected {EXPECTED_FRAME}. "
                         "Nothing was written")
    f["band"] = ""
    overlaps, thresholds = {}, {}
    for ds, g in f.groupby("dataset"):
        band, overlaps[ds], thresholds[ds] = assign_bands(g)
        f.loc[g.index, "band"] = band
    bands = bands_table(f, sizes, test_size)
    totals = {b: int((f.band == b).sum()) for b in BANDS}
    print(bands.round(3).to_string(index=False))
    print(f"\nconflicts per band: {totals}; expected: {EXPECTED_BANDS}")
    if totals != EXPECTED_BANDS:
        raise SystemExit("the bands differ from EXPECTED_BANDS. Nothing was written")

    cases = blind(f[f.band != ""].copy(), np.random.default_rng(SEED))
    cases["draw_case"], cases["draw_role"] = None, None
    sample_packages, in_sample = None, {}
    if sample_draw:
        sheet = pd.read_csv(os.path.join(sample_draw, "coding_sheet.csv"), dtype={"chunk_id": str})
        sheet = sheet.set_index(["dataset", "chunk_id"])
        keys = list(zip(cases.dataset, cases.chunk_id))
        cases["draw_case"] = [sheet.case.get(k) for k in keys]
        cases["draw_role"] = [sheet.role.get(k) for k in keys]
        in_sample = {r: int((cases.draw_role == r).sum()) for r in ("sample", "pilot")}
        sample_packages = os.path.join(sample_draw, "packages")

    mismatches, packages, reveals, too_large, reproduced, not_reproduced = build(cases, root, data_root,
                                                                                 sample_packages)
    cases["packaged"] = ~cases.case.isin(too_large)
    if mismatches:
        raise SystemExit(f"{len(mismatches)} packaged candidates do not match the similarity of the frame "
                         f"(first ones: {mismatches[:5]}). Nothing was written")
    if not_reproduced:
        raise SystemExit(f"{len(not_reproduced)} packages of the sample draw are not reproduced "
                         f"(first ones: {not_reproduced[:5]}). Nothing was written")

    today = datetime.date.today().isoformat()
    os.makedirs(sealed_dir, exist_ok=True)
    cases[["case", "dataset", "chunk_id", "band", "d", "sim_sbcr", "sim_mergegen", "candidate_a",
           "candidate_b", "sbcr_out_of_limits", "packaged", "draw_case", "draw_role"]].to_csv(sealed, index=False)
    os.makedirs(os.path.join(out, "packages"), exist_ok=True)
    os.makedirs(reveal, exist_ok=True)
    for case, text in packages.items():
        with open(os.path.join(out, "packages", f"{case}.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(os.path.join(reveal, f"{case}.md"), "w", encoding="utf-8") as fh:
            fh.write(reveals[case])
    sheet_path = os.path.join(out, "coding_sheet.csv")
    cases[cases.packaged][["case", "position", "dataset", "chunk_id"]].assign(role=ROLE, seed=SEED, draw_date=today)[
        ["case", "role", "position", "dataset", "chunk_id", "seed", "draw_date"]].to_csv(sheet_path, index=False)
    bands.to_csv(os.path.join(out, "bands.csv"), index=False)

    record = {
        "seed": SEED, "date": today, "script_sha256": sha256_file(__file__),
        "git_commit": commit, "git_dirty": dirty, "root": root, "data_root": data_root,
        "similarity": SIM, "role": ROLE, "cases": len(cases), "max_package_chars": MAX_PACKAGE_CHARS,
        "cases_packaged": len(packages), "cases_too_large": len(too_large),
        "sealed_file": os.path.basename(sealed), "sealed_sha256": sha256_file(sealed),
        "coding_sheet_sha256": sha256_file(sheet_path), "packages_sha256": packages_sha256(packages),
        "test_partition": test_size, "frame": sizes, "bands": totals, "expected_bands": EXPECTED_BANDS,
        "thresholds": thresholds, "conflicts_in_two_bands": overlaps,
        "sbcr_out_of_limits_in_bands": int(cases.sbcr_out_of_limits.sum()),
        "sbcr_out_of_limits_packaged": int(cases[cases.packaged].sbcr_out_of_limits.sum()),
        "cases_of_sample_draw": in_sample, "packages_of_sample_draw_reproduced": reproduced if sample_draw else None,
    }
    with open(os.path.join(out, "draw.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)

    print(f"\ncases: {len(cases)}; packaged: {len(packages)}; left out, package above {MAX_PACKAGE_CHARS:,} "
          f"characters: {len(too_large)}")
    print("the candidates of every package match the similarity of the frame")
    print(f"conflicts in two bands: {overlaps}")
    print(f"cases above SBCR's size limit: {record['sbcr_out_of_limits_in_bands']}, of them packaged, with an "
          f"empty SBCR candidate: {record['sbcr_out_of_limits_packaged']}")
    if sample_draw:
        print(f"cases of the sample draw in the frame: {in_sample}; their packages reproduced: {reproduced}")
    print(f"packages list sha256 {record['packages_sha256']}")
    print(f"\nwritten to {out}; sealed file at {sealed} (sha256 {record['sealed_sha256'][:12]}...); "
          f"reveal files in {reveal}")


if __name__ == "__main__":
    main()
