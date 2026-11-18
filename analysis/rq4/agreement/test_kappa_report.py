#!/usr/bin/env python3
"""Tests of the RQ4 agreement report on synthetic data.

The packages are written by `package()` of `build_packages.py`, so the empty and identical
candidates are read from packages as the real ones are written, which needs pandas and pylcs
(environment `sbcr-analise`). The sheet, the scheme and the annotator's records are made up
here, in the formats the docstring of `kappa_report.py` gives.

    python analysis/rq4/agreement/test_kappa_report.py
"""
import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import build_packages as bp  # noqa: E402
import kappa_report as kr  # noqa: E402

META = {"project": "owner/repo", "commit": "abc123", "file": "src/A.java", "constructs": "MethodDeclaration"}

SCHEME = {"version": "test-1", "dimensions": [
    {"id": "c", "name": "conflict", "categories": [
        {"code": "X", "name": "category x"}, {"code": "Y", "name": "category y"},
        {"code": "Z", "name": "other", "residual": True}]},
    {"id": "f", "name": "failure", "categories": [
        {"code": "F1", "name": "wrong side"},
        {"code": "NC", "name": "no candidate", "predefined": True},
        {"code": "ND", "name": "no difference between the candidates", "predefined": True},
        {"code": "NF", "name": "no candidate clearly further from the resolution", "predefined": True}]}]}

# case: (candidate A, candidate B), and per dimension (consensus or None, readings or None,
# annotator run 1). B1-03 has an empty candidate, B1-04 identical ones.
CANDS = {"B1-01": ("int a = 2;", "int a = 1;"), "B1-02": ("int a = 2;", "int a = 1;"),
         "B1-03": ("int a = 2;", ""), "B1-04": ("int a = 2;", "int  a=2 ;"),
         "B1-05": ("int a = 2;", "int a = 1;"), "B1-06": ("int a = 2;", "int a = 1;"),
         "P01": ("int a = 2;", "int a = 1;"), "P02": ("int a = 2;", "int a = 1;")}
LABELS = {
    "B1-01": {"c": ("X", None, "X"), "f": ("F1", None, "F1")},
    "B1-02": {"c": ("X", None, "X"), "f": ("F1", None, "NF")},
    "B1-03": {"c": ("Y", None, "Z"), "f": ("NC", None, "no candidate")},
    "B1-04": {"c": ("Z", None, "Z"), "f": ("ND", None, "ND")},
    "B1-05": {"c": (None, ("X", "Z"), "X"), "f": ("F1", None, "F1")},
    "B1-06": {"c": (None, ("Y", "X"), "Z"), "f": ("NF", None, "NF")},
    "P01": {"c": ("X", None, "X"), "f": ("F1", None, "F1")},
    "P02": {"c": ("Y", None, "Y"), "f": ("F1", None, "F1")},
}
RUN2 = {"B1-01": {"c": "X", "f": "F1"}, "B1-02": {"c": "Y", "f": "NF"}}


def package(case, cand_a, cand_b, v1="int a = 1;\n", sims=None):
    v2, res = "int a = 2;\n", "int a = 2;\n"
    if sims is None:
        s1, s2 = bp.sim(v1, res), bp.sim(v2, res)
        sims = {"v1": s1, "v2": s2, "parents": (s1 + s2) / 2}
    row = SimpleNamespace(case=case, dataset="dataset1", chunk_id="42")
    return bp.package(row, META, {"v1": v1, "v2": v2, "base": "int a = 0;\n", "resolution": res}, cand_a, cand_b,
                      bp.LANGUAGE["dataset1"], sims)


def sheet_row(case, labels):
    role, block = ("pilot", 0) if case.startswith("P") else ("sample", 1)
    row = {"case": case, "role": role, "block": block, "position": 1, "secondary": "", "notes": ""}
    for d, (cons, readings, _) in labels.items():
        row.update({f"dominant_code_{d}": cons or "",
                    f"no_consensus_{d}": "" if cons else "1",
                    f"reading_author1_{d}": readings[0] if readings else "",
                    f"reading_author2_{d}": readings[1] if readings else ""})
    return row


def record(case, k, codes, sha="s1", step="labeling", single=False, scheme_sha="sc1", desc_sha="d1"):
    out = {"case": case, "secondary": "", "residual_description": "", "justification": "j"}
    out.update({"code": codes["c"]} if single else {f"code_{d}": v for d, v in codes.items()})
    return {"case": case, "run": k, "step": step, "model_requested": "claude-opus-5-5", "effort": "high",
            "instructions_commit": "v1", "instructions_sha256": sha, "scheme_sha256": scheme_sha,
            "description_instructions_sha256": desc_sha, "output": out}


class PackageFlags(unittest.TestCase):
    def flags(self, a, b, v1="int a = 1;\n"):
        return kr.package_flags(kr.parse_package(package("B1-01", a, b, v1), "B1-01"))

    def test_empty_candidate(self):
        self.assertEqual(self.flags("int a = 2;", ""), (True, False))
        self.assertEqual(self.flags("int a = 2;", "int  a=2 ;"), (False, True))
        self.assertEqual(self.flags("int a = 2;", "int a = 1;"), (False, False))

    def test_an_empty_candidate_that_is_the_text_of_an_empty_version(self):
        # section 5.6 of the protocol, revision of 2026-10-12: coded by content, not as no candidate
        self.assertEqual(self.flags("int a = 2;", "", v1=""), (False, False))
        self.assertEqual(self.flags("", "", v1=""), (False, True))

    def test_an_ambiguous_split_reads_the_markers(self):
        # a version with a separator of its own and similarities that match neither split
        v1 = "<<<<<<< HEAD\nint a = 1;\n=======\nint a = 3;\n>>>>>>> other\n"
        sims = {"v1": 0.5, "v2": 0.5, "parents": 0.5}
        p = kr.parse_package(package("B1-01", "int a = 2;", "", v1, sims), "B1-01")
        self.assertEqual(p["split"], "ambiguous")
        self.assertEqual(kr.package_flags(p), (True, False))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.draw, self.ann = os.path.join(self.tmp, "draw"), os.path.join(self.tmp, "ann")
        os.makedirs(os.path.join(self.draw, "packages"))
        with open(os.path.join(self.draw, "coding_sheet.csv"), "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["case", "role", "block", "position", "dataset", "chunk_id"])
            for i, case in enumerate(CANDS, 1):
                w.writerow([case, "pilot" if case.startswith("P") else "sample", 0 if case.startswith("P") else 1,
                            i, "dataset1", "42"])
        for case, (a, b) in CANDS.items():
            with open(os.path.join(self.draw, "packages", f"{case}.md"), "w", encoding="utf-8") as fh:
                fh.write(package(case, a, b))
        self.scheme = os.path.join(self.tmp, "scheme.json")
        self.write_scheme(SCHEME)
        self.sheet = os.path.join(self.tmp, "recording_sheet.csv")
        self.write_sheet(LABELS)
        for case, dims in LABELS.items():
            self.write_record(record(case, 1, {d: v[2] for d, v in dims.items()}))
        for case, codes in RUN2.items():
            self.write_record(record(case, 2, codes))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_scheme(self, scheme):
        with open(self.scheme, "w", encoding="utf-8") as fh:
            json.dump(scheme, fh)

    def write_sheet(self, labels):
        rows = [sheet_row(case, dims) for case, dims in labels.items()]
        with open(self.sheet, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    def write_record(self, rec):
        os.makedirs(os.path.join(self.ann, rec["case"]), exist_ok=True)
        with open(os.path.join(self.ann, rec["case"], f"run{rec['run']}.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh)

    def run_report(self, blocks="1", out="out"):
        out = os.path.join(self.tmp, out)
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            kr.main(["--draw", self.draw, "--scheme", self.scheme, "--sheet", self.sheet, "--annotator", self.ann,
                     "--blocks", blocks, "--out", out])
        with open(os.path.join(out, "kappa_report.json"), encoding="utf-8") as fh:
            return json.load(fh), printed.getvalue()

    def refused(self, fragment, blocks="1"):
        with self.assertRaises(SystemExit) as e:
            self.run_report(blocks)
        self.assertIn(fragment, str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "out", "kappa_report.json")))


class Measures(unittest.TestCase):
    def test_kappa_by_hand(self):
        # po = 3/4; marginals a 2/4 and 1/4, b 2/4 and 3/4; pe = (2*1 + 2*3)/16 = 1/2
        self.assertAlmostEqual(kr.kappa([("a", "a"), ("a", "b"), ("b", "b"), ("b", "b")]), 0.5)
        self.assertEqual(kr.kappa([("a", "a"), ("a", "a")]), 1.0)
        self.assertIsNone(kr.kappa([]))

    def test_percentile_as_numpy(self):
        self.assertAlmostEqual(kr.percentile([4, 1, 3, 2], 2.5), 1.075)
        self.assertAlmostEqual(kr.percentile([4, 1, 3, 2], 97.5), 3.925)
        self.assertEqual(kr.percentile([7], 50), 7)

    def test_bootstrap_is_fixed_by_the_seed(self):
        pairs = [("a", "a")] * 20 + [("a", "b")] * 5 + [("b", "b")] * 20 + [("c", "c")] * 5
        first = kr.bootstrap(pairs)
        self.assertEqual(first, kr.bootstrap(pairs))
        self.assertNotEqual(first, kr.bootstrap(pairs, seed=kr.SEED + 1))
        self.assertLess(first[0], kr.kappa(pairs))
        self.assertGreater(first[1], kr.kappa(pairs))

    def test_worst_case_label(self):
        self.assertEqual(kr.worst_case_label("X", "Z", "X"), "Z")
        self.assertEqual(kr.worst_case_label("X", "Z", "Z"), "X")
        self.assertEqual(kr.worst_case_label("Y", "X", "Z"), "Y")


class Report(Fixture):
    def test_block_with_two_dimensions(self):
        rep, printed = self.run_report()
        self.assertEqual(rep["settings"]["seed"], kr.SEED)
        (b,) = rep["blocks"]
        self.assertTrue(b["counts_for_the_decision"])
        self.assertEqual(b["annotator"]["instructions_sha256"], "s1")
        c, f = b["dimensions"]["c"], b["dimensions"]["f"]
        self.assertEqual((c["with_consensus"], c["without_consensus"]), (4, 2))
        # consensus against annotator, B1-01 to B1-04: X/X, X/X, Y/Z, Z/Z; pe = (2*2 + 1*2)/16, kappa 0.6
        m = c["consensus_vs_annotator"]
        self.assertEqual((m["cases"], m["agreements"]), (4, 3))
        self.assertAlmostEqual(m["kappa"], 0.6)
        self.assertFalse(c["reaches_threshold"])
        self.assertFalse(b["annotator_approved"])
        # worst case adds B1-05 (readings X and Z, annotator X: label Z) and B1-06 (Y and X, annotator Z: Y)
        worst = [("X", "X"), ("X", "X"), ("Y", "Z"), ("Z", "Z"), ("Z", "X"), ("Y", "Z")]
        self.assertEqual((c["worst_case"]["cases"], c["worst_case"]["agreements"]), (6, 3))
        self.assertAlmostEqual(c["worst_case"]["kappa"], kr.kappa(worst))
        # the authors label by consensus only, so there is no kappa between them (revision of 2026-10-18)
        self.assertNotIn("between_authors", c)
        per = {x["code"]: (x["authors"], x["annotator"], x["both"]) for x in c["per_category"]}
        self.assertEqual(per, {"X": (2, 2, 2), "Y": (1, 0, 0), "Z": (1, 2, 1)})
        self.assertEqual(c["subsets"]["empty_candidate"], {"cases": 1, "with_consensus": 1, "agreements": 0})
        self.assertEqual(c["subsets"]["identical_candidates"], {"cases": 1, "with_consensus": 1, "agreements": 1})
        self.assertEqual(c["stability_against_run_1"], {"2": {"cases": 2, "agreements": 1, "kappa": 0.0}})
        # failure dimension: all six with consensus, the name "no candidate" read as NC, B1-02 F1/NF the only miss
        self.assertEqual(f["consensus_vs_annotator"]["agreements"], 5)
        self.assertTrue(f["reaches_threshold"])
        self.assertEqual(f["subsets"]["empty_candidate"]["agreements"], 1)
        per = {x["code"]: (x["authors"], x["annotator"], x["both"]) for x in f["per_category"]}
        self.assertEqual(per["NF"], (1, 2, 1))
        self.assertIn("| 1 | conflict | 6 | 2 | 0.600 (", printed)
        self.assertIn("NF no candidate clearly further from the resolution (predefined)", printed)
        self.assertIn("Annotator not approved by this block", printed)

    def test_pilot_counts_for_nothing(self):
        rep, printed = self.run_report("0")
        (b,) = rep["blocks"]
        self.assertFalse(b["counts_for_the_decision"])
        self.assertIsNone(b["annotator_approved"])
        self.assertEqual(b["cases"], 2)
        self.assertIn("does not count (pilot)", printed)

    def test_one_dimension(self):
        self.write_scheme({"version": "one", "dimensions": [SCHEME["dimensions"][0]]})
        self.write_sheet({case: {"c": dims["c"]} for case, dims in LABELS.items()})
        shutil.rmtree(self.ann)
        for case, dims in LABELS.items():
            self.write_record(record(case, 1, {"c": dims["c"][2]}, single=True))
        rep, _ = self.run_report()
        self.assertEqual(list(rep["blocks"][0]["dimensions"]), ["c"])
        self.assertAlmostEqual(rep["blocks"][0]["dimensions"]["c"]["consensus_vs_annotator"]["kappa"], 0.6)

    def test_does_not_overwrite(self):
        self.run_report()
        with self.assertRaises(SystemExit):
            self.run_report()


class Refusals(Fixture):
    def test_readings_in_a_case_with_consensus(self):
        labels = dict(LABELS, **{"B1-01": {**LABELS["B1-01"], "c": ("X", ("X", "Y"), "X")}})
        self.write_sheet(labels)
        self.refused("a case with consensus has readings")

    def test_equal_readings_without_consensus(self):
        labels = dict(LABELS, **{"B1-05": {**LABELS["B1-05"], "c": (None, ("X", "X"), "X")}})
        self.write_sheet(labels)
        self.refused("both readings are")

    def test_code_outside_the_scheme(self):
        labels = dict(LABELS, **{"B1-01": {**LABELS["B1-01"], "c": ("Q", None, "X")}})
        self.write_sheet(labels)
        self.refused("not a code of the scheme")

    def test_missing_run_1(self):
        os.remove(os.path.join(self.ann, "B1-03", "run1.json"))
        self.refused("B1-03: no run 1")

    def test_two_instruction_versions_in_one_block(self):
        self.write_record(record("B1-04", 1, {"c": "Z", "f": "ND"}, sha="s2"))
        self.refused("one frozen version")

    def test_two_schemes_in_one_block(self):
        self.write_record(record("B1-04", 1, {"c": "Z", "f": "ND"}, scheme_sha="sc2"))
        self.refused("one frozen version")

    def test_descriptions_from_two_instructions_in_one_block(self):
        self.write_record(record("B1-04", 1, {"c": "Z", "f": "ND"}, desc_sha="d2"))
        self.refused("one frozen version")

    def test_description_record(self):
        self.write_record(record("B1-02", 1, {"c": "X", "f": "F1"}, step="description"))
        self.refused("give the folder of the labeling step")

    def test_annotator_code_outside_the_scheme(self):
        self.write_record(record("B1-02", 1, {"c": "W", "f": "F1"}))
        self.refused("neither a code nor a name")

    def test_case_missing_from_the_sheet(self):
        self.write_sheet({k: v for k, v in LABELS.items() if k != "B1-06"})
        self.refused("B1-06 of block 1 is not in the sheet")

    def test_role_that_does_not_match_the_block(self):
        path = os.path.join(self.draw, "coding_sheet.csv")
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        rows[6][1] = "supplement"  # B1-06
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)
        self.refused("B1-06 of block 1 has the role 'supplement'")

    def test_sealed_file_in_the_draw(self):
        open(os.path.join(self.draw, "sealed_sample.csv"), "w").close()
        self.refused("must not read")


if __name__ == "__main__":
    unittest.main()
