"""Shared figure style. Colours come from the dataviz skill's validated default
palette (categorical slots 1-3 for batch identity, status `critical` plus slots 7
and 5 for the flag classes); the three batch colours were re-run through
`validate_palette.js` and pass the lightness, chroma, CVD-separation and
normal-vision checks on the light surface.

Batch identity is colour, flag class is colour AND dash pattern, so nothing in any
figure is distinguishable by colour alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr
from flags import CLASS_STYLE, CLASS_LABEL  # noqa: F401  (re-exported)

FIGDIR = HERE / "figures"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e3e2dd"
BATCH_COLORS = matr.BATCH_COLORS
BATCH_DATES = matr.BATCH_DATES

EOL = matr.EOL_THRESHOLD_AH
EOL75 = matr.EOL_75PCT_AH
# the batch that actually used the 75% criterion (Step 2, finding 13)
CRITERION_AH = {"2017-05-12": EOL, "2017-06-30": EOL75, "2018-04-12": EOL}


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "savefig.dpi": 150,
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
        "axes.edgecolor": INK2, "axes.linewidth": 0.6,
        "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK2, "ytick.color": INK2,
        "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.fontsize": 7.5,
        "figure.titlesize": 11,
    })


def line_style(cell_class: str, batch_date: str) -> dict:
    """Drawing kwargs for one cell: batch colour when unflagged, flag colour and
    dash pattern otherwise."""
    st = dict(CLASS_STYLE[cell_class])
    if st["color"] is None:
        st["color"] = BATCH_COLORS[batch_date]
    return {"color": st["color"], "linestyle": st["ls"],
            "linewidth": st["lw"], "alpha": st["alpha"], "zorder": st["z"]}


def class_legend(ax, classes, batch_date, loc="best", extra=()):
    """Legend keyed on flag class, always present when more than one class is
    drawn, so identity never rests on colour."""
    from matplotlib.lines import Line2D
    order = ["ok", "censored", "page_flagged", "data_flagged"]
    handles = []
    for c in order:
        if c not in classes:
            continue
        st = line_style(c, batch_date)
        handles.append(Line2D([], [], label=CLASS_LABEL[c], **st))
    handles.extend(extra)
    if len(handles) > 1:
        ax.legend(handles=handles, loc=loc)
    return handles


def figure_class_legend(fig, classes, ncol=4, y=0.925):
    """One legend for the whole figure, so per-panel legends cannot collide with
    the data. Always drawn when more than one flag class appears."""
    from matplotlib.lines import Line2D
    order = ["ok", "censored", "page_flagged", "data_flagged"]
    handles = [Line2D([], [], label=CLASS_LABEL[c],
                      **{**line_style(c, BATCH_DATES[0]), "color": CLASS_STYLE[c]["color"] or INK2})
               for c in order if c in classes]
    if len(handles) > 1:
        fig.legend(handles=handles, loc="upper center", ncol=ncol,
                   bbox_to_anchor=(0.5, y), frameon=False, fontsize=8)


def caption(fig, text):
    fig.text(0.005, 0.004, text, ha="left", va="bottom", fontsize=7, color=INK2,
             wrap=True)


def save(fig, name, caption_text=None, tight_rect=(0, 0.045, 1, 0.965)):
    FIGDIR.mkdir(exist_ok=True)
    if caption_text:
        caption(fig, caption_text)
    fig.tight_layout(rect=tight_rect)
    path = FIGDIR / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"wrote figures/{name}.png")
    return path


def clip_markers(ax, x, y, ymax, color):
    """Draw points that fall above the axis limit as upward triangles on the top
    edge instead of silently cropping them."""
    m = np.asarray(y) > ymax
    if m.any():
        ax.plot(np.asarray(x)[m], np.full(m.sum(), ymax), marker="^", ls="none",
                ms=4, mfc="none", mec=color, mew=0.9, zorder=6, clip_on=False)
    return int(m.sum())
