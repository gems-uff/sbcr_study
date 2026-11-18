#!/usr/bin/env python3
"""The two figures of the paper drawn from the data of partition 1.

- `rq1-rq2-time.pdf`: time per conflict of SBCR and MergeGen on the combination test subset of
  each dataset, on a logarithmic scale. The times are read with the functions of
  `analysis/rq1_rq3/times_per_language.py`, which check them against the wall times of the runs.
  MergeGen's time is end to end. SBCR's leaves out the conflicts above its 20,000-character limit,
  which have no time. Boxes span the quartiles, whiskers reach the furthest time within 1.5
  interquartile ranges of the box, and the times beyond them are drawn one by one.
- `rq4-bands.pdf`: histogram of d = Sim_SBCR - Sim_MergeGen in each dataset, in bins of 0.05
  centered on zero, with the limits of the two clear-win bands. The near-tie band lies inside the
  bin centered on zero and is not drawn. The frame and the bands are those of
  `analysis/rq4/build_scale.py`, and the script stops if the band counts differ from `bands.csv` of
  the coding at scale or the limits from its `draw.json`.

Runs in the `sbcr-analysis` environment. The PDFs carry no creation date, so a rerun on the same
data writes the same bytes.

Inputs: the root of partition 1 (`--root`) and the folder of the coding at scale (`--scale`, with
`bands.csv` and `draw.json`).
Outputs: the two PDFs in `--out`, and a PNG of each in `--png` when given.

    python analysis/figures/paper_figures.py --root <root of partition 1> --scale <rq4/scale> --out <dir>
"""
import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in ("rq1_rq3", "similarity", "rq4"):
    sys.path.insert(0, os.path.join(HERE, "..", folder))
import times_per_language as tpl  # noqa: E402
from draw_sample import ARM, BANDS, DATASETS, SBCR_SEED, assign_bands, build_frame  # noqa: E402
from sbcr_scores import OK, SIM, sbcr_chunk_ids  # noqa: E402
LABELS = {"dataset1": r"$Dataset1$", "dataset2_Java": r"$Dataset2_{Java}$",
          "dataset2_CSharp": r"$Dataset2_{C\#}$", "dataset2_JavaScript": r"$Dataset2_{JavaScript}$",
          "dataset2_TypeScript": r"$Dataset2_{TypeScript}$"}

# \linewidth of sn-jnl, 372 pt, so that the fonts print at the size set below
WIDTH = 5.15

# two colors told apart under color-vision deficiency, with enough contrast against white
SBCR_COLOR, MERGEGEN_COLOR = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#222222", "#666666", "#dddddd"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["cmr10"], "mathtext.fontset": "cm",
    "axes.formatter.use_mathtext": True, "font.size": 9, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
})


def save(fig, name, out, png):
    # no creation date, so that a rerun on the same data writes the same bytes
    fig.savefig(os.path.join(out, f"{name}.pdf"), bbox_inches="tight", metadata={"CreationDate": None})
    if png:
        fig.savefig(os.path.join(png, f"{name}.png"), bbox_inches="tight", dpi=200)
    plt.close(fig)


def times(root):
    """Per dataset, MergeGen's end-to-end times and SBCR's times on the combination subset."""
    out = {}
    for name in DATASETS:
        mg = tpl.load_mergegen(root, name, ARM)
        sb = tpl.load_sbcr(root, name, ARM, SBCR_SEED)
        comb = sbcr_chunk_ids(root, name, ARM)
        m = mg[mg.chunk_id.isin(comb)].end_to_end.to_numpy()
        s = sb[sb.chunk_id.isin(comb) & (sb.status == OK)].time_seconds.astype(float).to_numpy()
        if len(m) != len(comb) or (s <= 0).any():
            raise SystemExit(f"{name}: MergeGen times do not cover the subset, or an SBCR time is not positive")
        out[name] = (s, m)
        print(f"{name}: SBCR n {len(s)}, median {np.median(s):.3f} s; MergeGen n {len(m)}, median {np.median(m):.3f} s")
    return out


def plot_times(data):
    fig, ax = plt.subplots(figsize=(WIDTH, 2.8))
    flier = {"marker": "o", "markersize": 2, "markeredgewidth": 0, "alpha": 0.45}
    for i, name in enumerate(DATASETS):
        for offset, series, color, hatch in [(-0.19, data[name][0], SBCR_COLOR, None),
                                             (0.19, data[name][1], MERGEGEN_COLOR, "////")]:
            b = ax.boxplot(series, positions=[i + offset], widths=0.32, patch_artist=True,
                           flierprops={**flier, "markerfacecolor": color},
                           medianprops={"color": INK, "linewidth": 1.2},
                           whiskerprops={"color": MUTED}, capprops={"color": MUTED})
            box = b["boxes"][0]
            box.set(facecolor=color, edgecolor=INK, linewidth=0.6, alpha=0.85)
            if hatch:
                box.set_hatch(hatch)
    ax.set_yscale("log")
    ax.set_ylabel("Time per conflict (s)")
    # the four languages of Dataset2 under one bracket, since the full names do not fit
    ax.set_xticks(range(len(DATASETS)), [LABELS["dataset1"], r"$Java$", r"$C\#$", r"$JavaScript$", r"$TypeScript$"])
    below = blended_transform_factory(ax.transData, ax.transAxes)
    ax.plot([0.65, 4.35], [-0.15, -0.15], color=MUTED, linewidth=0.6, transform=below, clip_on=False)
    ax.text(2.5, -0.17, r"$Dataset2$", transform=below, ha="center", va="top", fontsize=8, color=INK)
    ax.set_xlim(-0.6, len(DATASETS) - 0.4)
    ax.yaxis.grid(True, which="major", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(handles=[Patch(facecolor=SBCR_COLOR, edgecolor=INK, label="SBCR"),
                       Patch(facecolor=MERGEGEN_COLOR, edgecolor=INK, hatch="////", label="MergeGen")],
              loc="upper left", frameon=False, ncol=2)
    return fig


def bands(root, scale):
    """The frame of `build_scale.py` with the band of each conflict, and the limits per dataset."""
    f, _ = build_frame(root, column=SIM)
    expected = pd.read_csv(os.path.join(scale, "bands.csv")).set_index(["dataset", "band"]).conflicts
    drawn = json.load(open(os.path.join(scale, "draw.json"), encoding="utf-8"))["thresholds"]
    frames, limits = {}, {}
    for name in DATASETS:
        g = f[f.dataset == name].copy()
        g["band"], _, thresholds = assign_bands(g)
        for band in BANDS:
            if (g.band == band).sum() != expected[(name, band)]:
                raise SystemExit(f"{name}, band {band}: {(g.band == band).sum()} conflicts, "
                                 f"{expected[(name, band)]} in bands.csv of the coding at scale")
        if not all(np.isclose(thresholds[k], drawn[name][k]) for k in thresholds):
            raise SystemExit(f"{name}: band limits differ from draw.json of the coding at scale")
        frames[name], limits[name] = g, thresholds
        print(f"{name}: {len(g)} conflicts, " + ", ".join(f"{b} {(g.band == b).sum()}" for b in BANDS)
              + ", limits " + ", ".join(f"{k} {v:.4f}" for k, v in thresholds.items()))
    return frames, limits


def plot_bands(frames, limits):
    edges = np.arange(-1.025, 1.026, 0.05)
    fig, axes = plt.subplots(3, 2, figsize=(WIDTH, 5.6), sharex=True)
    for ax, name in zip(axes.flat, DATASETS):
        g, t = frames[name], limits[name]
        lo, hi = -t["q3_negative_abs"], t["q3_positive"]
        ax.axvspan(-1.05, lo, color=MERGEGEN_COLOR, alpha=0.18, linewidth=0)
        ax.axvspan(hi, 1.05, color=SBCR_COLOR, alpha=0.18, linewidth=0)
        ax.hist(g.d, bins=edges, color="#7a7a7a", edgecolor="white", linewidth=0.4)
        for x, color in [(lo, MERGEGEN_COLOR), (hi, SBCR_COLOR)]:
            ax.axvline(x, color=color, linewidth=1.0, linestyle="--")
        ax.axvline(0, color=INK, linewidth=0.5)
        ax.set_title(f"{LABELS[name]} ($n$ = {len(g):,})", fontsize=9, color=INK)
        ax.set_xlim(-1.05, 1.05)
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_ylabel("Conflicts")
    legend = axes.flat[-1]
    legend.axis("off")
    legend.legend(handles=[Patch(facecolor=MERGEGEN_COLOR, alpha=0.35, label="Clear MergeGen win"),
                           Patch(facecolor=SBCR_COLOR, alpha=0.35, label="Clear SBCR win"),
                           Patch(facecolor="#7a7a7a", label="Conflicts per bin of 0.05")],
                  loc="center", frameon=False)
    for ax in [axes[2, 0], axes[1, 1]]:
        ax.set_xlabel(r"$d = \mathit{Sim}_{SBCR} - \mathit{Sim}_{MergeGen}$")
        ax.xaxis.set_tick_params(labelbottom=True)
    fig.tight_layout()
    return fig


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="root of partition 1")
    p.add_argument("--scale", required=True, help="folder of the coding at scale, with bands.csv and draw.json")
    p.add_argument("--out", required=True, help="folder of the two PDFs")
    p.add_argument("--png", help="folder for a PNG copy of each figure")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    for folder in [args.out, args.png]:
        if folder:
            os.makedirs(folder, exist_ok=True)

    save(plot_times(times(root)), "rq1-rq2-time", args.out, args.png)
    save(plot_bands(*bands(root, os.path.expanduser(args.scale))), "rq4-bands", args.out, args.png)


if __name__ == "__main__":
    main()
