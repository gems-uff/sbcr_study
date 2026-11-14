#!/usr/bin/env python3
"""Ties and wins per quartile of the imbalance.

The logistic model of `fit_models.R` leaves out the ties. The script reads `conflicts.csv` of
`build_table.py` and writes, per quartile of the imbalance over all conflicts, the share of ties,
the share of SBCR wins among the conflicts with a winner and the mean difference SBCR −
MergeGen, with a row for the conflicts with one empty version (imbalance 1) and a row for all.

Input and output: the folder of `build_table.py`, where it writes `ties_by_imbalance.csv`.

    python analysis/winner/ties_by_imbalance.py <folder>
"""
import argparse
import os

import pandas as pd


def summary(g, name):
    winners = g.sbcr_wins.notna()
    return {"group": name, "imbalance_min": g.imbalance.min(), "imbalance_max": g.imbalance.max(), "n": len(g),
            "ties": int((~winners).sum()), "ties_share": (~winners).mean(),
            "with_winner": int(winners.sum()), "sbcr_wins": int(g.sbcr_wins.sum()),
            "sbcr_wins_share": g.sbcr_wins[winners].mean() if winners.any() else float("nan"),
            "mean_difference": g.difference.mean()}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("folder")
    folder = os.path.expanduser(p.parse_args().folder)
    t = pd.read_csv(os.path.join(folder, "conflicts.csv"))

    # quartiles over all conflicts; equal edges (many conflicts at 1) merge into one bin
    t["quartile"] = pd.qcut(t.imbalance, 4, duplicates="drop")
    rows = [summary(g, f"quartile {i}") for i, (_, g) in enumerate(t.groupby("quartile", observed=True), start=1)]
    rows.append(summary(t[t.imbalance == 1], "one empty version"))
    rows.append(summary(t, "all"))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(folder, "ties_by_imbalance.csv"), index=False)

    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(out.round(4).to_string(index=False))
    print(f"\nwritten in {os.path.join(folder, 'ties_by_imbalance.csv')}")


if __name__ == "__main__":
    main()
