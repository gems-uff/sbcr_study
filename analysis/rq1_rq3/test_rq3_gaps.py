#!/usr/bin/env python3
"""Tests of `rq3_gaps.py`, on synthetic data.

The root is made up here in the layout `compare_approaches.py` and `sbcr_scores.py` read: the
test partitions in `data/`, `sbcr_similarities.csv`, the SBCR result spreadsheets and candidates
in `sbcr/eval_*`, and the MergeGen similarity files in `mergeGen/JIT`. Needs pandas, SciPy and
openpyxl (environment `sbcr-analysis`).

    python analysis/rq1_rq3/test_rq3_gaps.py
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))
import rq3_gaps as rg  # noqa: E402
from sbcr_scores import load_sbcr_similarities  # noqa: E402
DS1 = ["11", "12", "13", "14"]
JAVA = ["21", "22", "23", "24", "25"]


def sbcr_folder(root, target, seed, sims, out_of_limits=()):
    """One SBCR evaluation: its spreadsheet, a candidate per `ok` chunk, and the CSV rows."""
    folder = os.path.join(root, "sbcr", f"eval_{target}_mg_s{seed}")
    os.makedirs(os.path.join(folder, "RESULTS"))
    os.makedirs(os.path.join(folder, "OUTPUT"))
    status = [{"chunk_id": c, "status": "OUT_OF_LIMITS" if c in out_of_limits else "ok"} for c in sims]
    status += [{"chunk_id": c, "status": "OUT_OF_LIMITS"} for c in out_of_limits if c not in sims]
    pd.DataFrame(status).to_excel(os.path.join(folder, "RESULTS", "results.xlsx"), index=False)
    rows = []
    for c, s in sims.items():
        if c in out_of_limits:
            continue
        open(os.path.join(folder, "OUTPUT", c), "w").write("candidate")
        rows.append({"target": target, "arm": "mg", "seed": seed, "partition": "mg", "chunk_id": c,
                     "sim_lcs_full": s, "sim_lcs_no_whitespace": s, "exact_match_full": float(s == 1.0),
                     "sim_original": s, "time": 1.0})
    return rows


def mergegen_file(root, test_set, model, sims):
    folder = os.path.join(root, "mergeGen", "JIT", f"{test_set}_mg", f"model_{model}_mg")
    os.makedirs(folder)
    pd.DataFrame({"chunk_id": list(sims), "sim_lcs_full": list(sims.values()),
                  "sim_lcs_no_whitespace": list(sims.values()),
                  "exact_match_full": [float(s == 1.0) for s in sims.values()]}).to_csv(
        os.path.join(folder, "similarities.csv"), index=False)


def make_root(root, second_seed=None, in_progress_seed=None):
    os.makedirs(os.path.join(root, "data"))
    json.dump({"chunk_id": [int(c) for c in DS1]}, open(os.path.join(root, "data", "dataset1_mg_testing.json"), "w"))
    json.dump({"chunk_id": [int(c) for c in JAVA]},
              open(os.path.join(root, "data", "dataset2_Java_mg_combination_testing.json"), "w"))
    rows = []
    rows += sbcr_folder(root, "dataset1", "3022024", dict(zip(DS1, [1.0, 0.5, 0.8, 0.7])))
    rows += sbcr_folder(root, "rq3_ds1", "3022024", dict(zip(DS1, [0.9, 0.5, 0.6, 0.9])))
    # chunk 25 is above SBCR's size limit under both configurations
    rows += sbcr_folder(root, "dataset2_Java", "3022024", dict(zip(JAVA, [0.6, 0.7, 0.8, 0.9, 0.0])),
                        out_of_limits={"25"})
    rows += sbcr_folder(root, "rq3_java", "3022024", dict(zip(JAVA, [0.5, 0.7, 0.9, 0.6, 0.0])),
                        out_of_limits={"25"})
    if second_seed:
        for target, ids in (("dataset1", DS1), ("rq3_ds1", DS1)):
            rows += sbcr_folder(root, target, second_seed, dict.fromkeys(ids, 0.2))
        for target in ("dataset2_Java", "rq3_java"):
            rows += sbcr_folder(root, target, second_seed, dict.fromkeys(JAVA, 0.2), out_of_limits={"25"})
    if in_progress_seed:
        # a run still writing its spreadsheet: unreadable, and absent from the CSV
        folder = os.path.join(root, "sbcr", f"eval_rq3_java_mg_s{in_progress_seed}")
        os.makedirs(os.path.join(folder, "RESULTS"))
        os.makedirs(os.path.join(folder, "OUTPUT"))
        open(os.path.join(folder, "RESULTS", "results.xlsx"), "wb").write(b"not a spreadsheet")
        open(os.path.join(folder, "OUTPUT", "21"), "w").write("candidate")
    pd.DataFrame(rows).to_csv(os.path.join(root, "sbcr_similarities.csv"), index=False)
    mergegen_file(root, "dataset1", "dataset1", dict(zip(DS1, [1.0, 1.0, 0.9, 0.8])))
    mergegen_file(root, "dataset1", "dataset2_Java", dict(zip(DS1, [1.0, 0.9, 0.9, 0.9])))
    mergegen_file(root, "dataset2_Java", "dataset2_Java", dict(zip(JAVA, [0.9, 0.8, 1.0, 0.7, 0.6])))
    mergegen_file(root, "dataset2_Java", "dataset1", dict(zip(JAVA, [0.9, 0.9, 1.0, 0.7, 0.5])))


def run(root, seeds):
    evaluated = rg.evaluated_sets(root)
    with contextlib.redirect_stdout(io.StringIO()):
        sb = load_sbcr_similarities(root, seeds=seeds)
    return rg.gaps(rg.sbcr_by_target(sb, seeds, evaluated),
                   rg.mergegen_by_model(rg.load_mergegen(root, evaluated), evaluated))


class Compare(unittest.TestCase):
    def test_hand_computed(self):
        own = pd.DataFrame({"chunk_id": DS1, "sim": [1.0, 0.5, 0.8, 0.7], "em": [1.0, 0, 0, 0]})
        other = pd.DataFrame({"chunk_id": DS1, "sim": [0.9, 0.5, 0.6, 0.9], "em": [0.0, 0, 0, 0]})
        r = rg.compare(own, other)
        # differences 0.1, 0, 0.2, -0.2; nonzero |d| ranked 1, 2.5, 2.5
        self.assertAlmostEqual(r["gap"], 0.025)
        self.assertAlmostEqual(r["rank_biserial"], (1 + 2.5 - 2.5) / 6)
        self.assertEqual((r["own_closer"], r["tie"], r["other_closer"]), (0.5, 0.25, 0.25))
        half = 1.96 * np.std([0.1, 0, 0.2, -0.2], ddof=1) / 2
        self.assertAlmostEqual(r["ci_low"], 0.025 - half)
        self.assertAlmostEqual(r["ci_high"], 0.025 + half)
        self.assertAlmostEqual(r["own_exact"], 0.25)

    def test_pairs_by_conflict_not_by_order(self):
        own = pd.DataFrame({"chunk_id": ["a", "b"], "sim": [1.0, 0.0], "em": [0, 0]})
        other = pd.DataFrame({"chunk_id": ["b", "a"], "sim": [0.0, 1.0], "em": [0, 0]})
        self.assertEqual(rg.compare(own, other)["tie"], 1.0)

    def test_different_conflicts_stop(self):
        own = pd.DataFrame({"chunk_id": ["a", "b"], "sim": [1.0, 0.0], "em": [0, 0]})
        other = pd.DataFrame({"chunk_id": ["a", "c"], "sim": [0.0, 1.0], "em": [0, 0]})
        with self.assertRaises(RuntimeError):
            rg.compare(own, other)

    def test_residue_of_a_tie_stops(self):
        # an exact tie passes
        own = frame(["1", "2"], [0.1, 0.5])
        other = frame(["1", "2"], [0.1, 0.25])
        self.assertEqual(rg.compare(own, other)["tie"], 0.5)
        # SBCR's gap 0.3 − 0.2 and MergeGen's 0.1 − 0.0 are equal, but differ by about 3e-17 in floating point
        sbcr = {"dataset1": frame(DS1, [0.3, 0.5, 0.5, 0.5]), "rq3_ds1": frame(DS1, [0.2, 0.5, 0.5, 0.5]),
                "dataset2_Java": frame(JAVA, [0.5] * 5), "rq3_java": frame(JAVA, [0.5] * 5)}
        mergegen = {("dataset1", "dataset1"): frame(DS1, [0.1, 0.5, 0.5, 0.5]),
                    ("dataset1", "dataset2_Java"): frame(DS1, [0.0, 0.5, 0.5, 0.5]),
                    ("dataset2_Java", "dataset2_Java"): frame(JAVA, [0.5] * 5),
                    ("dataset2_Java", "dataset1"): frame(JAVA, [0.5] * 5)}
        with self.assertRaises(RuntimeError):
            rg.gap_difference(sbcr, mergegen)
        with self.assertRaises(RuntimeError):
            rg.check_ties(pd.Series([0.0, 0.25, 1e-17]))

    def test_holm(self):
        np.testing.assert_allclose(rg.holm([0.01, 0.04, 0.03, 0.5]), [0.04, 0.09, 0.09, 0.5])


def frame(ids, sims):
    return pd.DataFrame({"chunk_id": ids, "sim": sims, "em": [float(x == 1.0) for x in sims]})


class GapDifference(unittest.TestCase):
    def test_hand_computed(self):
        sbcr = {"dataset1": frame(DS1, [1.0, 0.5, 0.75, 0.5]), "rq3_ds1": frame(DS1, [0.75, 0.5, 0.5, 1.0]),
                "dataset2_Java": frame(JAVA, [0.5] * 5), "rq3_java": frame(JAVA, [0.5] * 5)}
        mergegen = {("dataset1", "dataset1"): frame(DS1, [1.0, 1.0, 0.75, 0.5]),
                    ("dataset1", "dataset2_Java"): frame(DS1[::-1], [0.5, 0.75, 0.75, 1.0]),
                    ("dataset2_Java", "dataset2_Java"): frame(JAVA, [0.5] * 5),
                    ("dataset2_Java", "dataset1"): frame(JAVA, [0.5] * 5)}
        r = rg.gap_difference(sbcr, mergegen).set_index("test_set").loc["dataset1"]
        # SBCR's gaps 0.25, 0, 0.25, -0.5; MergeGen's 0, 0.25, 0, 0 (paired by chunk id, not by order);
        # differences 0.25, -0.25, 0.25, -0.5, ranked 2, 2, 2, 4
        self.assertAlmostEqual(r.difference, -0.0625)
        self.assertAlmostEqual(r.sbcr_gap - r.mergegen_gap, r.difference)
        self.assertEqual((r.sbcr_gap_larger, r.equal, r.mergegen_gap_larger), (0.5, 0.0, 0.5))
        self.assertAlmostEqual(r.rank_biserial, (2 + 2 - 2 - 4) / 10)
        half = 1.96 * np.std([0.25, -0.25, 0.25, -0.5], ddof=1) / 2
        self.assertAlmostEqual(r.ci_low, -0.0625 - half)

    def test_different_conflicts_stop(self):
        sbcr = {"dataset1": frame(DS1, [1.0] * 4), "rq3_ds1": frame(DS1, [0.5] * 4),
                "dataset2_Java": frame(JAVA, [0.5] * 5), "rq3_java": frame(JAVA, [0.5] * 5)}
        other_ids = DS1[:3] + ["99"]
        mergegen = {("dataset1", "dataset1"): frame(other_ids, [1.0] * 4),
                    ("dataset1", "dataset2_Java"): frame(other_ids, [0.5] * 4),
                    ("dataset2_Java", "dataset2_Java"): frame(JAVA, [0.5] * 5),
                    ("dataset2_Java", "dataset1"): frame(JAVA, [0.5] * 5)}
        with self.assertRaises(RuntimeError):
            rg.gap_difference(sbcr, mergegen)


class SyntheticRoot(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_four_comparisons(self):
        make_root(self.root)
        t = run(self.root, ["3022024"]).set_index(["approach", "test_set"])
        self.assertEqual(len(t), 4)
        self.assertAlmostEqual(t.loc[("SBCR", "dataset1"), "gap"], 0.025)
        self.assertAlmostEqual(t.loc[("MergeGen", "dataset1"), "gap"], 0.0)
        self.assertEqual(t.loc[("SBCR", "dataset2_Java"), "n"], 5)
        np.testing.assert_allclose(t.p_holm, rg.holm(t.p))

    def test_gap_difference_on_the_root(self):
        make_root(self.root)
        evaluated = rg.evaluated_sets(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            sb = load_sbcr_similarities(self.root, seeds=["3022024"])
        sbcr = rg.sbcr_by_target(sb, ["3022024"], evaluated)
        mergegen = rg.mergegen_by_model(rg.load_mergegen(self.root, evaluated), evaluated)
        t = rg.gaps(sbcr, mergegen).set_index(["approach", "test_set"]).gap
        d = rg.gap_difference(sbcr, mergegen).set_index("test_set")
        self.assertEqual(list(d.n), [4, 5])
        for test_set in ("dataset1", "dataset2_Java"):
            self.assertAlmostEqual(d.loc[test_set, "difference"],
                                   t[("SBCR", test_set)] - t[("MergeGen", test_set)])
        np.testing.assert_allclose(d.p_holm, rg.holm(d.p))

    def test_out_of_limits_is_a_tie(self):
        make_root(self.root)
        t = run(self.root, ["3022024"]).set_index(["approach", "test_set"])
        r = t.loc[("SBCR", "dataset2_Java")]
        # differences 0.1, 0, -0.1, 0.3 and 0 for chunk 25, scored 0 under both configurations
        self.assertAlmostEqual(r.gap, 0.3 / 5)
        self.assertAlmostEqual(r.tie, 2 / 5)

    def test_seed_in_progress_is_not_opened(self):
        make_root(self.root, in_progress_seed="20260904")
        t = run(self.root, ["3022024"])
        self.assertEqual(len(t), 4)
        with self.assertRaises(Exception):
            run(self.root, ["3022024", "20260904"])

    def test_mean_over_seeds(self):
        make_root(self.root, second_seed="31337")
        t = run(self.root, ["3022024", "31337"]).set_index(["approach", "test_set"])
        r = t.loc[("SBCR", "dataset1")]
        self.assertAlmostEqual(r.own_mean, (np.mean([1.0, 0.5, 0.8, 0.7]) + 0.2) / 2)
        self.assertAlmostEqual(r.gap, 0.025 / 2)

    def test_missing_conflict_stops(self):
        make_root(self.root)
        evaluated = rg.evaluated_sets(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            loaded = load_sbcr_similarities(self.root, seeds=["3022024"])
        loaded = loaded[~((loaded.target == "rq3_ds1") & (loaded.chunk_id == "12"))]
        with self.assertRaises(RuntimeError):
            rg.sbcr_by_target(loaded, ["3022024"], evaluated)

    def test_check_against_comparison(self):
        make_root(self.root)
        t = run(self.root, ["3022024"])
        rows = []
        for r in t.itertuples():
            for analysis, mean in (("rq1_rq2", r.own_mean), ("rq3", r.other_mean)):
                rows.append({"analysis": analysis, "dataset": r.test_set, "arm": "mg",
                             "approach": r.approach, "mean": mean})
        c = pd.DataFrame(rows).pivot_table(index=["analysis", "dataset", "arm"], columns="approach",
                                           values="mean").reset_index()
        c = c.rename(columns={"SBCR": "sbcr", "MergeGen": "mergegen"})
        c.to_csv(os.path.join(self.root, "comparison.csv"), index=False)
        self.assertLessEqual(rg.check_against_comparison(t, self.root), rg.COMPARISON_TOLERANCE)
        c.loc[0, "sbcr"] += 0.001
        c.to_csv(os.path.join(self.root, "comparison.csv"), index=False)
        with self.assertRaises(RuntimeError):
            rg.check_against_comparison(t, self.root)


if __name__ == "__main__":
    unittest.main()
