"""Fig 11 -- what the analysis set actually contains, after the agreed decisions."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plotstyle import (apply_style, save, line_style, figure_class_legend,
                       BATCH_COLORS, BATCH_DATES, INK2)

apply_style()
SOH_EOL = 0.8


def fig11():
    cells = pd.read_csv(HERE / "analysis_set_cells.csv")
    cyc = pd.read_csv(HERE / "analysis_set_cycles.csv")
    cls = cells.set_index("cell_uid")["cell_class"].to_dict()

    fig = plt.figure(figsize=(15, 8.6))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.25, 1], hspace=0.38, wspace=0.24)

    # --- row 1: truncated SOH trajectories
    all_classes = set()
    for col, d in enumerate(BATCH_DATES):
        ax = fig.add_subplot(gs[0, col])
        sub = cyc[(cyc.batch_date == d) & cyc.is_measured_cycle & ~cyc.is_artifact_cycle]
        n = 0
        for uid, g in sub.groupby("cell_uid"):
            c = cls[uid]
            all_classes.add(c)
            ax.plot(g.cycle, g.soh, **line_style(c, d))
            n += 1
        ax.axhline(SOH_EOL, color="#d03b3b", lw=1.0, ls=(0, (6, 3)), zorder=5)
        ax.text(0.99, SOH_EOL, "80% SOH = 0.88 Ah ", transform=ax.get_yaxis_transform(),
                ha="right", va="bottom", fontsize=7, color="#d03b3b")
        ax.set_ylim(0.78, 1.01)
        ax.set_xlabel("cycle number")
        ax.set_title(f"{d}  ({n} cells)", color=BATCH_COLORS[d])
        if col == 0:
            ax.set_ylabel("SOH  ($Q_D$ / 1.1 Ah nominal)")

    # --- row 2 left: the target
    ax = fig.add_subplot(gs[1, 0])
    bins = np.logspace(np.log10(140), np.log10(2400), 26)
    for d in BATCH_DATES:
        g = cells[(cells.batch_date == d) & cells.has_eol_label]
        ax.hist(g.eol_cycle_80pct_soh, bins=bins, histtype="step", lw=1.5,
                color=BATCH_COLORS[d], label=f"{d} (n={len(g)})")
    ax.set_xscale("log")
    ax.set_xlabel("cycle at which 80% SOH is crossed")
    ax.set_ylabel("cells")
    ax.set_title("The target, by batch", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=7)

    # --- row 2 middle: what is in and out
    ax = fig.add_subplot(gs[1, 1])
    rows = [
        ("physical cells", len(cells)),
        ("with 80% SOH label", int(cells.has_eol_label.sum())),
        ("default train set", int((cells.use_for_trajectory & cells.has_eol_label).sum())),
        ("censored", int(cells.censored.sum())),
        ("continuations (D3)", int(cells.is_continuation.sum())),
        ("Severson subset", int(cells.in_paper_124.sum())),
    ]
    y = np.arange(len(rows))[::-1]
    ax.barh(y, [v for _, v in rows], color="#2a78d6", alpha=0.8, height=0.6)
    for yy, (lab, v) in zip(y, rows):
        ax.text(v + 2, yy, str(v), va="center", fontsize=8, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels([lab for lab, _ in rows], fontsize=8)
    ax.set_xlim(0, 168); ax.set_xlabel("cells")
    ax.tick_params(axis="y", length=0)
    ax.set_title("What the set contains", fontsize=9.5)
    ax.grid(axis="y", visible=False)

    # --- row 2 right: target vs policy, the thing the model must generalise over
    ax = fig.add_subplot(gs[1, 2])
    g = cells[cells.has_eol_label]
    for d in BATCH_DATES:
        gg = g[g.batch_date == d]
        ax.plot(gg.policy_C1, gg.eol_cycle_80pct_soh, marker="o", ls="none", ms=5,
                mfc=BATCH_COLORS[d], mec="none", alpha=0.8, label=d)
    ax.set_yscale("log")
    ax.set_xlabel("first-step charge rate $C_1$ (C)")
    ax.set_ylabel("cycles to 80% SOH")
    ax.set_title("Target vs charging policy", fontsize=9.5)
    ax.legend(loc="upper right", fontsize=7)

    fig.suptitle("Fig 11 — The analysis set: SOH trajectories truncated at 80% SOH, "
                 f"{len(cells)} cells, {len(cyc):,} cycles", y=0.995)
    figure_class_legend(fig, all_classes, y=0.952)
    save(fig, "fig11_analysis_set",
         "Row 1: every cell's SOH trajectory, truncated at its 80% SOH crossing, with the placeholder and "
         "capacity-artifact cycles hidden for legibility only (they are flagged, not removed, in "
         "analysis_set_cycles.csv). Flagged cells are drawn, not excluded. Row 2 left: the target. The three "
         "batches sit on visibly different levels — medians 841, 481 and 1004 cycles — which is why batch_date "
         "must stay in the model: the batches differ in charging policy AND in CV cutoff, rest scheme and "
         "baseline temperature. Row 2 right: the same target against first-step charge rate, the main designed "
         "source of variation.", tight_rect=(0, 0.05, 1, 0.945))


if __name__ == "__main__":
    fig11()
