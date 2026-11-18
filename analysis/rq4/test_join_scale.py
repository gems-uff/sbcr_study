#!/usr/bin/env python3
"""Tests of the join of the RQ4 labels at scale with band and tool, on synthetic data.

The packages are written by `package()` of `build_packages.py`, as the real ones are, which needs
pandas and pylcs (environment `sbcr-analysis`). The sealed file, the draw record, the scheme, the
annotator's records and the coding sheet are made up here, in the formats `build_scale.py`,
and `run_annotator.py` write.

    python analysis/rq4/test_join_scale.py
"""
import contextlib
import csv
import hashlib
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
import build_packages as bp  # noqa: E402
import join_scale as js  # noqa: E402

META = {"project": "owner/repo", "commit": "abc123", "file": "src/A.java", "constructs": "MethodDeclaration"}

SCHEME = {"version": "test-1", "dimensions": [
    {"id": "merge", "name": "Merge characteristic", "categories": [
        {"code": "C4", "name": "Large conflict"}, {"code": "C2", "name": "Overlapping edits"},
        {"code": "C1", "name": "Adjacent independent edits"}]},
    {"id": "cand", "name": "Candidate characteristic", "categories": [
        {"code": "FN", "name": "No candidate", "predefined": True},
        {"code": "FD", "name": "No difference between the candidates", "predefined": True},
        {"code": "FU", "name": "Neither candidate clearly further from the resolution", "predefined": True},
        {"code": "F1", "name": "Misses one version's change"},
        {"code": "F4", "name": "Adds a change the resolution discarded"}]}]}

# case: band, tool behind A, sim SBCR, sim MergeGen, above SBCR's limit, packaged, draw case,
# candidates A and B, closer, merge code, candidate code
CASES = {
    "S0001": ("sbcr", "sbcr", 0.9, 0.5, False, True, "", ("int a = 2;", "int a = 1;"), "A", "C1", "F1"),
    "S0002": ("mergegen", "mergegen", 0.4, 0.9, False, True, "", ("int a = 2;", "int a = 1;"), "A", "C2", "F4"),
    "S0003": ("tie", "sbcr", 0.7, 0.7, False, True, "", ("int a = 2;", "int  a=2 ;"), "equal", "C1", "FD"),
    "S0004": ("mergegen", "sbcr", 0.0, 0.8, True, True, "", ("", "int a = 2;"), "B", "C4", "FN"),
    "S0005": ("tie", "mergegen", 0.5, 0.5, True, False, "", None, None, None, None),
    "S0006": ("tie", "mergegen", 0.6, 0.61, False, True, "B1-01", ("int a = 2;", "int a = 1;"), "unclear", "C1", "FU"),
}
SHEET = [  # case, block, consensus merge, consensus cand
    ("P01", 0, "C1", "F1"), ("B1-01", 1, "C1", "FU"), ("B1-02", 1, "C2", "F1")]
APPROVAL = {"B1-01": ("C1", "F1"), "B1-02": ("C2", "F1")}


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def package(case, cand_a, cand_b):
    v1, v2, res = "int a = 1;\n", "int a = 2;\n", "int a = 2;\n"
    s1, s2 = bp.sim(v1, res), bp.sim(v2, res)
    row = SimpleNamespace(case=case, dataset="dataset1", chunk_id="42")
    return bp.package(row, META, {"v1": v1, "v2": v2, "base": "int a = 0;\n", "resolution": res}, cand_a, cand_b,
                      bp.LANGUAGE["dataset1"], {"v1": s1, "v2": s2, "parents": (s1 + s2) / 2})


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def write_rows(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


class JoinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        t = self.tmp
        self.draw, self.sealed = os.path.join(t, "draw"), os.path.join(t, "sealed", "sealed_scale.csv")
        self.desc, self.lab = os.path.join(t, "desc"), os.path.join(t, "lab")
        self.app, self.approval = os.path.join(t, "app"), os.path.join(t, "approval")
        self.scheme, self.sheet = os.path.join(self.app, "scheme.json"), os.path.join(self.app, "exports", "sheet.csv")
        self.sample = os.path.join(t, "sealed", "sealed_sample.csv")
        self.out = os.path.join(t, "sealed", "join")
        for d in (os.path.join(self.draw, "packages"), os.path.dirname(self.sealed), os.path.dirname(self.sheet)):
            os.makedirs(d, exist_ok=True)
        scheme_text = write_json(self.scheme, SCHEME)
        self.scheme_sha = sha_text(scheme_text)

        sealed, sheet = [], []
        for case, (band, a, s, m, out_lim, packaged, draw_case, cands, closer, cm, cc) in CASES.items():
            sealed.append({"case": case, "dataset": "dataset1", "chunk_id": case[1:], "band": band, "d": s - m,
                           "sim_sbcr": s, "sim_mergegen": m, "candidate_a": a,
                           "candidate_b": "mergegen" if a == "sbcr" else "sbcr", "sbcr_out_of_limits": out_lim,
                           "packaged": packaged, "draw_case": draw_case, "draw_role": "sample" if draw_case else ""})
            if not packaged:
                continue
            sheet.append({"case": case, "role": "scale", "position": len(sheet) + 1, "dataset": "dataset1",
                          "chunk_id": case[1:], "seed": 1, "draw_date": "2026-10-23"})
            text = package(case, *cands)
            with open(os.path.join(self.draw, "packages", f"{case}.md"), "w", encoding="utf-8") as fh:
                fh.write(text)
            desc_text = write_json(os.path.join(self.desc, case, "run1.json"),
                                   {"step": "description", "case": case, "package_sha256": sha_text(text),
                                    "output": {"case": case, "closer": closer}})
            write_json(os.path.join(self.lab, case, "run1.json"),
                       {"step": "labeling", "case": case, "package_sha256": sha_text(text),
                        "description_sha256": sha_text(desc_text), "scheme_sha256": self.scheme_sha,
                        "output": {"case": case, "code_merge": cm, "code_cand": cc}})
        write_rows(self.sealed, js.SEALED_COLUMNS, sealed)
        write_rows(os.path.join(self.draw, "coding_sheet.csv"), list(sheet[0]), sheet)
        write_json(os.path.join(self.draw, "draw.json"),
                   {"sealed_sha256": sha_file(self.sealed),
                    "coding_sheet_sha256": sha_file(os.path.join(self.draw, "coding_sheet.csv")),
                    "packages_sha256": js.packages_sha256(os.path.join(self.draw, "packages"))})

        rows = []
        for case, block, cm, cc in SHEET:
            rows.append({"case": case, "role": "pilot" if block == 0 else "sample", "block": block,
                         "dominant_code_merge": cm, "dominant_code_cand": cc, "no_consensus_merge": "",
                         "no_consensus_cand": ""})
        write_rows(self.sheet, list(rows[0]), rows)
        for case, (cm, cc) in APPROVAL.items():
            write_json(os.path.join(self.approval, case, "run1.json"),
                       {"step": "labeling", "case": case, "instructions_sha256": "i", "scheme_sha256": "s",
                        "output": {"case": case, "code_merge": cm, "code_cand": cc}})
        write_rows(self.sample, js.SAMPLE_COLUMNS + ["band"],
                   [{"case": "P01", "role": "pilot", "block": 0, "candidate_a": "mergegen", "candidate_b": "sbcr",
                     "band": "tie"},
                    {"case": "B1-01", "role": "sample", "block": 1, "candidate_a": "sbcr", "candidate_b": "mergegen",
                     "band": "tie"},
                    {"case": "B1-02", "role": "sample", "block": 1, "candidate_a": "mergegen", "candidate_b": "sbcr",
                     "band": "sbcr"}])
        self.old_sha = js.SAMPLE_SEALED_SHA256, js.SCHEME_SHA256
        js.SAMPLE_SEALED_SHA256, js.SCHEME_SHA256 = sha_file(self.sample), self.scheme_sha

    def tearDown(self):
        js.SAMPLE_SEALED_SHA256, js.SCHEME_SHA256 = self.old_sha
        shutil.rmtree(self.tmp)

    def args(self, **change):
        a = {"--sealed": self.sealed, "--draw": self.draw, "--scheme": self.scheme, "--description": self.desc,
             "--labeling": self.lab, "--sheet": self.sheet, "--approval": self.approval,
             "--sample-sealed": self.sample, "--out": self.out}
        a.update(change)
        return [x for k, v in a.items() if v is not None for x in (k, v)]

    def run_join(self, **change):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            js.main(self.args(**change), expected_cases=len(CASES))
        return out.getvalue()

    def read(self, name):
        with open(os.path.join(self.out, name), encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def refuses(self, message, **change):
        with self.assertRaises(SystemExit) as cm:
            self.run_join(**change)
        self.assertIn(message, str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.out, "joined.csv")))

    def test_join(self):
        printed = self.run_join()
        rows = {r["case"]: r for r in self.read("joined.csv")}
        self.assertEqual(len(rows), 6)
        expected = {  # further by the annotator, by the similarity, tool of the empty candidate
            "S0001": ("mergegen", "mergegen", ""), "S0002": ("sbcr", "sbcr", ""),
            "S0003": ("equal", "equal", ""), "S0004": ("sbcr", "sbcr", "sbcr"),
            "S0005": ("", "equal", ""), "S0006": ("unclear", "sbcr", "")}
        for case, (fa, fm, empty) in expected.items():
            self.assertEqual((rows[case]["further_annotator"], rows[case]["further_measured"],
                              rows[case]["empty_candidate_tool"]), (fa, fm, empty), case)
        self.assertEqual((rows["S0004"]["code_merge"], rows["S0004"]["code_cand"]), ("C4", "FN"))
        self.assertEqual((rows["S0005"]["code_merge"], rows["S0005"]["packaged"]), ("", "False"))

        freq = self.read("frequencies.csv")

        def get(cut, band, further, dim, code):
            f = [x for x in freq if (x["cut"], x["band"], x["further"], x["dimension"], x["code"]) ==
                 (cut, band, further, dim, code)]
            self.assertEqual(len(f), 1)
            return int(f[0]["cases"]), int(f[0]["of"])

        self.assertEqual(get("all", "", "", "cand", "FN"), (1, 5))
        self.assertEqual(get("band", "mergegen", "", "cand", "F4"), (1, 2))
        self.assertEqual(get("band", "tie", "", "merge", "C1"), (2, 2))
        self.assertEqual(get("band_further", "mergegen", "sbcr", "cand", "FN"), (1, 2))
        self.assertEqual(get("band_further", "tie", "unclear", "cand", "FU"), (1, 1))

        with open(os.path.join(self.out, "join_report.json"), encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertEqual(report["cases"]["tie"], {"conflicts": 3, "labeled": 2, "not_labeled": 1, "above_sbcr_limit": 1})
        self.assertEqual(report["cases"]["all"]["conflicts"], 6)
        self.assertEqual(report["further"]["tie"]["unclear"]["sbcr"], 1)
        self.assertEqual(report["empty_candidates"],
                         [{"band": "mergegen", "tool": "sbcr", "cases": 1, "above_sbcr_limit": 1, "codes": {"FN": 1}}])
        b1 = report["block1"]
        self.assertEqual((b1["cases"], b1["in_bands"]), (2, 1))
        self.assertEqual(b1["measures"]["cand"]["scale_vs_authors"]["agreements"], 1)
        self.assertEqual(b1["measures"]["cand"]["scale_vs_approval"]["agreements"], 0)
        self.assertEqual(b1["measures"]["merge"]["approval_vs_authors"]["kappa"], 1.0)
        # the pair of the approval over all of block 1 also counts B1-02, which left the bands
        self.assertEqual(b1["measures"]["cand"]["approval_vs_authors"]["cases"], 1)
        self.assertEqual((b1["measures"]["cand"]["approval_vs_authors_all"]["cases"],
                          b1["measures"]["cand"]["approval_vs_authors_all"]["agreements"]), (2, 1))
        self.assertIn("approval, authors, all of block 1", printed)
        self.assertEqual(report["git_commit"], js.git_state()[0])
        self.assertIsNotNone(report["git_commit"])
        block1 = self.read("block1.csv")
        self.assertEqual([(r["draw_case"], r["case"], r["scale_cand"], r["approval_cand"]) for r in block1],
                         [("B1-01", "S0006", "FU", "F1")])
        # B1-02 left the bands, and the tool behind its candidates is still given
        self.assertEqual([(r["case"], r["candidate_a"], r["candidate_b"], r["case_at_scale"])
                          for r in self.read("sample_tools.csv")],
                         [("P01", "mergegen", "sbcr", ""), ("B1-01", "sbcr", "mergegen", "S0006"),
                          ("B1-02", "mergegen", "sbcr", "")])
        self.assertEqual(report["sample_tools"], {"cases": 3, "at_scale": 1})
        self.assertIn("## Candidate characteristic per band", printed)
        self.assertNotIn("interval", printed.replace("no sampling margin", ""))

    def test_without_block1(self):
        self.run_join(**{"--sheet": None, "--approval": None, "--sample-sealed": None})
        self.assertEqual(self.read("block1.csv"), [])
        self.assertEqual(self.read("sample_tools.csv"), [])

    def test_sheet_needs_approval(self):
        self.refuses("go together", **{"--approval": None})

    def test_sealed_changed(self):
        with open(self.sealed, "a", encoding="utf-8") as fh:
            fh.write("\n")
        self.refuses("does not have the SHA-256")

    def test_sample_sealed_changed(self):
        with open(self.sample, "a", encoding="utf-8") as fh:
            fh.write("\n")
        self.refuses("sealed file of the sample draw")

    def test_packages_changed(self):
        with open(os.path.join(self.draw, "packages", "S0002.md"), "a", encoding="utf-8") as fh:
            fh.write(" ")
        self.refuses("not those that draw.json records")

    def test_label_of_another_package(self):
        path = os.path.join(self.lab, "S0002", "run1.json")
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["package_sha256"] = "other"
        write_json(path, rec)
        self.refuses("not written from")

    def test_scheme_not_frozen(self):
        js.SCHEME_SHA256 = "other"
        self.refuses("is not the frozen scheme")

    def test_label_of_another_description(self):
        path = os.path.join(self.desc, "S0001", "run1.json")
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["output"]["explanation"] = "changed"
        write_json(path, rec)
        self.refuses("another description")

    def test_label_with_another_scheme(self):
        path = os.path.join(self.lab, "S0003", "run1.json")
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["scheme_sha256"] = "other"
        write_json(path, rec)
        self.refuses("another scheme")

    def test_label_missing(self):
        shutil.rmtree(os.path.join(self.lab, "S0006"))
        self.refuses("no run 1 of the labeling step")

    def test_code_not_in_scheme(self):
        path = os.path.join(self.lab, "S0001", "run1.json")
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["output"]["code_cand"] = "F9"
        write_json(path, rec)
        self.refuses("neither a code nor a name")

    def test_wrong_frame_size(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            js.main(self.args(), expected_cases=1985)
        self.assertIn("has 6 cases", str(cm.exception))

    def test_out_inside_an_input(self):
        self.refuses("which the analysts or the annotator read", **{"--out": os.path.join(self.lab, "join")})
        self.refuses("which the analysts or the annotator read", **{"--out": os.path.join(self.app, "join")})

    def test_out_inside_git(self):
        self.refuses("inside a Git work tree", **{"--out": os.path.join(HERE, "join-test-out")})
        self.assertFalse(os.path.exists(os.path.join(HERE, "join-test-out")))

    def test_no_overwrite(self):
        self.run_join()
        with self.assertRaises(SystemExit) as cm:
            self.run_join()
        self.assertIn("already holds a join", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
