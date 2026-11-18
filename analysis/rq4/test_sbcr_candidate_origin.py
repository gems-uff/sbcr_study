#!/usr/bin/env python3
"""Tests of the origin of SBCR's candidates and of the score of the resolution, on synthetic conflicts.

The functions that read the root and the join need the root of partition 1, where
`sbcr_candidate_origin.py` checks the score of every SBCR candidate against its result spreadsheet.
These tests cover the parts that do not need the root: the origin categories, the search space,
the score as `sbcr/sbcr_evaluate.py` computes it, and the summaries.
Environment `sbcr-analysis` (pandas, numpy and pylcs).

    python analysis/rq4/test_sbcr_candidate_origin.py
"""
import os
import sys
import unittest

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "sbcr"))
import sbcr_candidate_origin as so  # noqa: E402

V1 = "int a = 1;\nint b = 2;\nint c = 3;\n"
V2 = "int a = 1;\nint b = 20;\nint c = 3;\nint d = 4;\n"
BASE = "int a = 1;\nint b = 2;\nint c = 3;\n"


class Origin(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(so.origin("", V1, V2, BASE), ("empty", ""))

    def test_exact_version(self):
        self.assertEqual(so.origin(V2, V1, V2, BASE), ("version_exact", "v2"))

    def test_final_line_break(self):
        v1 = V1.rstrip("\n")  # a version without a line break at its end
        self.assertEqual(so.origin(v1 + "\n", v1, V2, BASE), ("version_but_final_line_breaks", "v1"))

    def test_blank_line(self):
        cand = "int a = 1;\n\nint b = 20;\nint c = 3;\nint d = 4;\n"
        self.assertEqual(so.origin(cand, V1, V2, BASE), ("version_but_whitespace", "v2"))

    def test_base(self):
        v1 = "x\na\n"
        v2 = "x\nb\n"
        self.assertEqual(so.origin("x\n", v1, v2, "x\n"), ("base_but_whitespace", ""))

    def test_version_before_base(self):
        # V1 changed only whitespace, so a copy of V1 is also the base; the version comes first
        v1 = "int  a = 1;\n"
        self.assertEqual(so.origin("int a = 1;\n", v1, "int a = 2;\n", "int a = 1;\n"),
                         ("version_but_whitespace", "v1"))

    def test_both_versions(self):
        self.assertEqual(so.origin("a\n", "a", " a", None), ("version_but_final_line_breaks", "v1"))
        self.assertEqual(so.origin("a \n", "a", " a", None), ("version_but_whitespace", "both"))

    def test_other(self):
        self.assertEqual(so.origin("int a = 1;\nint d = 4;\n", V1, V2, BASE), ("other", ""))


class SearchSpace(unittest.TestCase):
    def test_interleaving(self):
        self.assertTrue(so.in_search_space("int a = 1;\nint b = 20;\nint c = 3;\nint d = 4;\n", V1, V2))
        self.assertTrue(so.in_search_space("int b = 2;\nint b = 20;\n", V1, V2))

    def test_order_of_a_version(self):
        self.assertFalse(so.in_search_space("int c = 3;\nint a = 1;\nint a = 1;\nint a = 1;\n", V1, V2))

    def test_line_in_no_version(self):
        self.assertFalse(so.in_search_space("int e = 5;\n", V1, V2))

    def test_line_used_twice(self):
        # a line present once in each version can appear twice, once from each
        self.assertTrue(so.in_search_space("int a = 1;\nint a = 1;\n", V1, V2))
        self.assertFalse(so.in_search_space("int d = 4;\nint d = 4;\n", V1, V2))

    def test_needs_the_frontier(self):
        # a greedy choice of the first version that has the line fails here
        v1, v2 = "x\ny\n", "y\nx\n"
        self.assertTrue(so.in_search_space("y\nx\ny\n", v1, v2))
        self.assertTrue(so.in_search_space("x\ny\nx\n", v1, v2))
        self.assertFalse(so.in_search_space("x\nx\nx\n", v1, v2))

    def test_pareto(self):
        self.assertEqual(so.pareto({(1, 5), (2, 3), (3, 3), (4, 1), (2, 6)}), [(1, 5), (2, 3), (4, 1)])


class Score(unittest.TestCase):
    def test_equal_texts(self):
        self.assertEqual(so.sbcr_gestalt("abc", "abc"), 1)

    def test_formula(self):
        # LCS of "abcd" and "abxd" is "abd"
        self.assertAlmostEqual(so.sbcr_gestalt("abcd", "abxd"), 2 * 3 / 8)

    def test_both_empty(self):
        self.assertEqual(so.sbcr_gestalt("", ""), 1)

    def test_one_empty(self):
        self.assertEqual(so.sbcr_gestalt("", "a"), 0)

    def test_read_as_latin1(self):
        # "é" is written as two bytes in UTF-8 and read back as two characters
        self.assertEqual(so.as_written("é"), "Ã©")
        self.assertAlmostEqual(so.sbcr_gestalt("é", "e"), 0)
        self.assertAlmostEqual(so.sbcr_gestalt("éa", "ea"), 2 * 1 / 5)

    def test_fitness_is_the_mean(self):
        c = "int a = 1;\nint b = 2;\n"
        self.assertAlmostEqual(so.sbcr_fitness(c, V1, V2), (so.sbcr_gestalt(c, V1) + so.sbcr_gestalt(c, V2)) / 2)

    def test_matches_sbcr_evaluate(self):
        try:
            import sbcr_evaluate
        except Exception as e:  # its module-level setup needs the folders of an SBCR run
            self.skipTest(f"sbcr_evaluate.py not importable here: {e}")
        for c in ("int a = 1;\nint b = 20;\n", "é\n", V1):
            self.assertAlmostEqual(so.sbcr_fitness(c, V1, V2), sbcr_evaluate.evaluate(c, V1, V2))

    def test_resolution_as_candidate(self):
        self.assertEqual(so.as_sbcr_candidate("a\nb"), "a\nb\n")
        self.assertEqual(so.as_sbcr_candidate("a\r\nb\n"), "a\nb\n")

    def test_comparison(self):
        self.assertEqual(so.comparison(0.5, 0.5 + 1e-12), "equal")
        self.assertEqual(so.comparison(0.6, 0.5), "resolution_higher")
        self.assertEqual(so.comparison(0.4, 0.5), "candidate_higher")


class Measure(unittest.TestCase):
    def test_check_against_stored(self):
        c = "int a = 1;\nint b = 2;\nint c = 3;\nint d = 4;\n"
        good = so.measure(c, V1, V2, BASE, V2, so.sbcr_fitness(c, V1, V2))
        self.assertTrue(good["fitness_check"])
        self.assertEqual(good["comparison"], "resolution_higher" if good["fitness_resolution"] >
                         good["fitness_candidate"] else good["comparison"])
        bad = so.measure(c, V1, V2, BASE, V2, 0.1)
        self.assertFalse(bad["fitness_check"])
        self.assertEqual(bad["comparison"], "")

    def test_candidate_is_resolution(self):
        c = "int a = 1;\n\nint b = 20;\nint c = 3;\nint d = 4;\n"  # V2 with a blank line
        self.assertTrue(so.measure(c, V1, V2, BASE, V2, so.sbcr_fitness(c, V1, V2))["candidate_is_resolution"])
        self.assertFalse(so.measure(V1 + "x\n", V1, V2, BASE, V2, None)["candidate_is_resolution"])

    def test_empty_candidate(self):
        m = so.measure("", V1, V2, BASE, V2, None)
        self.assertEqual((m["origin"], m["comparison"], m["fitness_check"]), ("empty", "", False))


class Tables(unittest.TestCase):
    def conflicts(self):
        rows = [
            {"dataset": "d1", "band": "mergegen", "sbcr_out_of_limits": False, "origin": "version_but_whitespace",
             "resolution_is_version": False, "resolution_in_space": True, "fitness_check": True,
             "comparison": "candidate_higher", "candidate_is_resolution": False},
            {"dataset": "d1", "band": "mergegen", "sbcr_out_of_limits": False, "origin": "other",
             "resolution_is_version": False, "resolution_in_space": True, "fitness_check": True,
             "comparison": "candidate_higher", "candidate_is_resolution": True},
            {"dataset": "d1", "band": "mergegen", "sbcr_out_of_limits": False, "origin": "base_but_whitespace",
             "resolution_is_version": False, "resolution_in_space": True, "fitness_check": True,
             "comparison": "resolution_higher", "candidate_is_resolution": False},
            {"dataset": "d1", "band": "tie", "sbcr_out_of_limits": False, "origin": "other",
             "resolution_is_version": True, "resolution_in_space": False, "fitness_check": True,
             "comparison": "equal", "candidate_is_resolution": False},
            {"dataset": "d1", "band": "mergegen", "sbcr_out_of_limits": True, "origin": None,
             "resolution_is_version": False, "resolution_in_space": False, "fitness_check": False,
             "comparison": None, "candidate_is_resolution": False},
            {"dataset": "d1", "band": "mergegen", "sbcr_out_of_limits": False, "origin": "other",
             "resolution_is_version": False, "resolution_in_space": True, "fitness_check": False,
             "comparison": "", "candidate_is_resolution": False},
            {"dataset": "d1", "band": "mergegen", "sbcr_out_of_limits": False, "origin": "empty",
             "resolution_is_version": False, "resolution_in_space": False, "fitness_check": False,
             "comparison": "", "candidate_is_resolution": False},
        ]
        return pd.DataFrame(rows)

    def test_origin_table(self):
        t = so.origin_table(self.conflicts(), "band").set_index("band")
        self.assertEqual(t.loc["mergegen", "processed"], 5)
        self.assertEqual(t.loc["mergegen", "empty"], 1)
        self.assertEqual(t.loc["mergegen", "version_but_whitespace"], 1)
        self.assertEqual(t.loc["mergegen", "base_but_whitespace"], 1)
        self.assertEqual(t.loc["tie", "resolution_is_version"], 1)

    def test_comparison_table(self):
        t = so.comparison_table(self.conflicts(), "band").set_index("band")
        self.assertEqual(t.loc["mergegen", "checked"], 3)  # the out-of-limits and the failed check are left out
        self.assertEqual(t.loc["mergegen", "check_failed"], 1)  # counted apart; the out-of-limits is not
        self.assertEqual(t.loc["tie", "check_failed"], 0)
        self.assertEqual(t.loc["mergegen", "in_space"], 3)
        self.assertEqual(t.loc["mergegen", "in_space_same"], 1)  # equal to the resolution, not compared
        self.assertEqual(t.loc["mergegen", "in_space_candidate_higher"], 1)
        self.assertEqual(t.loc["mergegen", "in_space_resolution_higher"], 1)
        self.assertEqual(t.loc["tie", "outside_equal"], 1)


if __name__ == "__main__":
    unittest.main()
