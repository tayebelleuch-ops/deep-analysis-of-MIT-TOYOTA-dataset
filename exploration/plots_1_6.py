"""Step 3, figures 1-6: capacity fade, continuations, cycle life, IR, temperature,
capacity-artifact detection. All read-only; everything lands in exploration/figures/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr
from checks import _meta, _valid_summary, batch_median_tavg
from plotstyle import (apply_style, save, line_style, class_legend, figure_class_legend,
                       CLASS_LABEL, BATCH_COLORS, BATCH_DATES, CRITERION_AH, EOL, EOL75,
                       INK2, clip_markers)

TABLES = HERE / "tables"
apply_style()


def _flags():
    df = pd.read_csv(TABLES / "cell_flags.csv")
    return {(r.batch_date, r.channel): r.cell_class for r in df.itertuples()}


# ---------------------------------------------------------------- figure 1
def fig01_capacity_fade():
    flags = _flags()
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.9), sharey=True)
    YMAX = 1.13
    all_classes = set()
    for ax, d in zip(axes, BATCH_DATES):
        recs = _meta()[d]
        classes, nclip = set(), 0
        for r in recs:
            s, _ = _valid_summary(r)
            cls = flags[(d, r.channel)]
            classes.add(cls)
            ax.plot(s["cycle"], s["QDischarge"], **line_style(cls, d))
            nclip += clip_markers(ax, s["cycle"], s["QDischarge"], YMAX,
                                  line_style(cls, d)["color"])
        ax.axhline(EOL, color="#d03b3b", lw=1.0, ls=(0, (6, 3)), zorder=5)
        ax.text(0.99, EOL, "0.88 Ah = 80% of nominal ", transform=ax.get_yaxis_transform(),
                ha="right", va="bottom", fontsize=7, color="#d03b3b")
        if CRITERION_AH[d] == EOL75:
            ax.axhline(EOL75, color="#6250d6", lw=1.0, ls=(0, (2, 2)), zorder=5)
            ax.text(0.01, EOL75, " 0.825 Ah = 75% — this batch's actual stop",
                    transform=ax.get_yaxis_transform(), ha="left", va="bottom",
                    fontsize=7, color="#6250d6")
        ax.set_title(f"{d}  ({len(recs)} cells)", color=BATCH_COLORS[d])
        ax.set_xlabel("cycle number")
        ax.set_ylim(0.80, YMAX)
        if nclip:
            ax.text(0.01, 0.97, f"{nclip} points above axis", transform=ax.transAxes,
                    fontsize=7, color=INK2, va="top")
        all_classes |= classes
    axes[0].set_ylabel("discharge capacity $Q_D$ (Ah)")
    figure_class_legend(fig, all_classes)
    fig.suptitle("Fig 1 — Discharge capacity vs cycle, one line per cell, "
                 f"{sum(len(_meta()[d]) for d in BATCH_DATES)} struct rows over 3 batches", y=0.995)
    save(fig, "fig01_capacity_fade",
         "y-axis floor is 0.80 Ah so nothing is cut above the 0.88 Ah line. Points above 1.13 Ah "
         "(2017-05-12 ch17 reaches 2.88 Ah at cycle 40) are drawn as hollow triangles on the top edge, not dropped. "
         "2017-06-30 stops at 0.825 Ah, not 0.88 Ah — the two batches do not share an end-of-life criterion.",
         tight_rect=(0, 0.05, 1, 0.90))


# ---------------------------------------------------------------- figure 2
def fig02_continuations():
    inv = pd.read_csv(HERE / "cell_inventory.csv")
    cont = inv[inv.is_continuation].sort_values("channel")
    meta = {d: {r.channel: r for r in _meta()[d]} for d in BATCH_DATES}
    fig, axes = plt.subplots(2, len(cont), figsize=(16, 6.4))
    for col, (_, row) in enumerate(cont.iterrows()):
        segs = [s.split(":ch") for s in row.all_segments.split(" | ")]
        xs, ys, bounds = [], [], []
        off = 0.0
        for d, ch in segs:
            r = meta[d][int(ch)]
            xs.append(r.summary["cycle"] + off)
            ys.append(r.summary["QDischarge"])
            off += len(r.summary["cycle"])
            bounds.append(off)
        junction = bounds[0]
        for ax, zoom in ((axes[0, col], False), (axes[1, col], True)):
            for (d, ch), x, y in zip(segs, xs, ys):
                ax.plot(x, y, color=BATCH_COLORS[d], lw=1.0,
                        label=f"{d} ch{int(ch)}" if not zoom else None)
            ax.axvline(junction, color="#6250d6", lw=1.1, ls="--", zorder=5)
            ax.axhline(EOL, color="#d03b3b", lw=0.8, ls=(0, (6, 3)), zorder=4)
            if zoom:
                ax.set_xlim(junction - 60, junction + 60)
                ax.set_ylim(0.93, 1.09)
                ax.set_xlabel("joined cycle number")
            else:
                ax.set_ylim(0.85, 1.10)
                ax.set_title(f"{row.barcode}\nch{int(row.channel)}  "
                             f"{row.policy_canonical}  ({row.n_cycles_per_segment} cycles)",
                             fontsize=8)
                ax.legend(loc="lower left", fontsize=7)
        if col == 0:
            axes[0, col].set_ylabel("discharge capacity $Q_D$ (Ah)")
            axes[1, col].set_ylabel("$Q_D$ (Ah), zoom at junction")
    fig.suptitle("Fig 2 — The 5 cells paused after 2017-05-12 and resumed in 2017-06-30, "
                 "joined on barcode (5 physical cells)")
    save(fig, "fig02_continuation_junction",
         "Dashed violet line = the junction between the two struct rows. Top row: whole joined record. "
         "Bottom row: +/-60 cycles around the junction. The pause itself was short: the batch dates are 49 days "
         "apart and these cells cycled for ~44-45 of them, implying a gap of roughly 4-6 days (approximate -- it "
         "assumes batch_date is the start date and uses the cycle-100 duration, which overstates cycling time "
         "slightly as cycles shorten with age). The 2017-05-12 page says the pause 'lead to a rise in "
         "capacity upon resuming the tests'. Every one of the five shows a DROP instead: -0.0033, -0.0093, -0.0093, "
         "-0.0028 and -0.0100 Ah (median of the 10 cycles each side). For ch2, ch3 and ch6 that is 8-18x the cell's "
         "own fade over 10 cycles, so it is a real step, not continued ageing. Cycle numbers after the junction are "
         "the second segment's own 1..N shifted by the first segment's length — the raw files carry no common clock. "
         "ch1's visible oscillation before the junction is its chronic single-cycle artifact (finding U3).")


# ---------------------------------------------------------------- figure 3
def fig03_cycle_life():
    flags = _flags()
    inv = pd.read_csv(HERE / "cell_inventory.csv")
    inv = inv[inv.in_struct].copy()
    inv["policy_plot"] = inv.policy_canonical
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6),
                             gridspec_kw={"width_ratios": [23, 43, 8]})
    rng = np.random.default_rng(0)
    for ax, d in zip(axes, BATCH_DATES):
        g = inv[inv.batch_date == d].copy()
        order = (g.groupby("policy_plot")["cycle_life_cycles"].median()
                 .sort_values().index.tolist())
        pos = {p: i for i, p in enumerate(order)}
        for _, r in g.iterrows():
            x = pos[r.policy_plot] + rng.uniform(-0.18, 0.18)
            if r.censored:
                # plot at the last recorded cycle with an up-arrow: a lower bound
                ax.plot(x, r.n_cycles_recorded, marker="^", ms=7, mfc="none",
                        mec="#d03b3b", mew=1.3, zorder=4)
            else:
                cls = flags.get((r.batch_date, r.channel), "ok")
                mec, mew = ("none", 0)
                if cls in ("page_flagged", "data_flagged"):
                    mec, mew = (line_style(cls, d)["color"], 1.4)
                ax.plot(x, r.cycle_life_cycles, marker="o", ms=5,
                        mfc=BATCH_COLORS[d], mec=mec, mew=mew, alpha=0.9, zorder=3)
        ax.set_yscale("log")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(order, rotation=90, fontsize=6.5)
        ax.set_title(f"{d}  ({len(g)} cells, {len(order)} policies)", color=BATCH_COLORS[d])
        ax.set_ylim(140, 2600)
        n_cens = int(g.censored.sum())
        h = [Line2D([], [], marker="o", ls="none", ms=5, mfc=BATCH_COLORS[d],
                    mec="none", label="reached criterion (true cycle life)")]
        if n_cens:
            h.append(Line2D([], [], marker="^", ls="none", ms=7, mfc="none",
                            mec="#d03b3b", mew=1.3,
                            label=f"censored, lower bound ({n_cens})"))
        for cls in ("page_flagged", "data_flagged"):
            h.append(Line2D([], [], marker="o", ls="none", ms=5, mfc=BATCH_COLORS[d],
                            mec=line_style(cls, d)["color"], mew=1.4,
                            label=CLASS_LABEL[cls]))
        ax.legend(handles=h, loc="upper left")
    axes[0].set_ylabel("cycle life (cycles, log scale)")
    fig.suptitle("Fig 3 — Cycle life by batch and charging policy (log scale); "
                 "every cell shown, so within-policy spread is visible")
    save(fig, "fig03_cycle_life_by_policy",
         "One marker per cell, jittered horizontally within its policy; policies ordered by median cycle life. "
         "Censored cells (hollow red triangle) are plotted at their LAST RECORDED cycle, which is a lower bound, "
         "not a cycle life. 2017-06-30 runs ~1 cell per policy by design, so within-policy spread is only "
         "readable for 2017-05-12 (2 per policy) and 2018-04-12 (3-8 per policy). "
         "The 5 continued cells appear under 2017-05-12 (their first batch) with their JOINED cycle life, which is "
         "why 3.6C(80%)-3.6C and 4C(80%)-4C reach 1400-2240 cycles; 2017-06-30 therefore shows 43 cells, not 48. "
         "Cycle life is not comparable across batches: 2017-06-30 was cycled to 0.825 Ah, the others to 0.88 Ah.")


# ---------------------------------------------------------------- figure 4
def fig04_internal_resistance():
    flags = _flags()
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=True)
    for ax, d in zip(axes, BATCH_DATES):
        recs = _meta()[d]
        classes, n_bad = set(), 0
        for r in recs:
            s, _ = _valid_summary(r)
            ir, cyc = s["IR"], s["cycle"]
            cls = flags[(d, r.channel)]
            classes.add(cls)
            st = line_style(cls, d)
            ax.plot(cyc, ir, **st)
            bad = ~np.isfinite(ir) | (ir <= 0)
            if bad.any():
                n_bad += int(bad.sum())
                ax.plot(cyc[bad], np.full(bad.sum(), 0.0135), marker="x", ls="none",
                        ms=6, mew=1.2, color="#d03b3b", zorder=6)
        ax.set_title(f"{d}  ({len(recs)} cells, {n_bad} implausible IR cycles)",
                     color=BATCH_COLORS[d])
        ax.set_xlabel("cycle number")
        ax.set_ylim(0.013, 0.026)
        extra = [Line2D([], [], marker="x", ls="none", ms=6, mew=1.2, color="#d03b3b",
                        label="IR = 0 exactly (plotted on the floor)")] if n_bad else []
        class_legend(ax, classes, d, loc="upper left", extra=extra)
    axes[0].set_ylabel(r"internal resistance ($\Omega$)")
    fig.suptitle("Fig 4 — Internal resistance vs cycle, one line per cell")
    save(fig, "fig04_internal_resistance",
         "No IR value is NaN anywhere in the three batches. 22 cycles across 19 cells record IR = 0.0 exactly "
         "(19 cycles in 2017-05-12, 3 in 2017-06-30, none in 2018-04-12); these are drawn as red crosses on the "
         "axis floor rather than left to distort the lines. Normal range is 0.014-0.024 ohm.")


# ---------------------------------------------------------------- figure 5
def fig05_temperature():
    flags = _flags()
    tc = pd.read_csv(TABLES / "thermocouple_outliers.csv")
    drift = pd.read_csv(TABLES / "chamber_drift.csv").set_index("batch_date")
    fig = plt.figure(figsize=(14, 9.6))
    gs = fig.add_gridspec(3, 3, height_ratios=[1, 1, 0.95], hspace=0.45, wspace=0.22)
    all_classes = set()
    for col, d in enumerate(BATCH_DATES):
        recs = _meta()[d]
        for row, field in enumerate(("Tavg", "Tmax")):
            ax = fig.add_subplot(gs[row, col])
            for r in recs:
                s_, _ = _valid_summary(r)
                cls = flags[(d, r.channel)]
                all_classes.add(cls)
                ax.plot(s_["cycle"], s_[field], **line_style(cls, d))
            ax.set_ylim(28, 45)
            if row == 0:
                ax.set_title(f"{d}  ({len(recs)} cells)", color=BATCH_COLORS[d])
            else:
                ax.set_xlabel("cycle number")
            if col == 0:
                ax.set_ylabel(f"{field} (°C)")

    # row 3, panel 1: the chamber moving under the whole batch
    ax = fig.add_subplot(gs[2, 0])
    for d in BATCH_DATES:
        x, y = batch_median_tavg(d)
        ax.plot(x, y, color=BATCH_COLORS[d], lw=1.4,
                label=f"{d}  (range {drift.loc[d, 'batch_median_range_C']:.2f} °C)")
    ax.set_xlabel("cycle number")
    ax.set_ylabel("batch-median $T_{avg}$ (°C)")
    ax.set_title("Chamber drift: the whole batch moves together", fontsize=9)
    ax.legend(loc="lower right", fontsize=7)

    # row 3, panel 2: per-cell baseline
    ax = fig.add_subplot(gs[2, 1])
    rngen = np.random.default_rng(1)
    for i, d in enumerate(BATCH_DATES):
        g = tc[tc.batch_date == d]
        for _, r in g.iterrows():
            st = line_style(flags[(d, r.channel)], d)
            ax.plot(i + rngen.uniform(-0.22, 0.22), r.Tmin_early_C, marker="o", ms=5,
                    mfc=st["color"], mec="none", alpha=0.85)
    ax.axhline(30.0, color=INK2, lw=0.8, ls=":")
    ax.text(0.99, 30.0, "chamber setpoint 30 °C ", transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", fontsize=7, color=INK2)
    ax.set_xticks(range(3))
    ax.set_xticklabels([d for d in BATCH_DATES], fontsize=7.5)
    ax.set_ylim(27.5, 33.2)
    ax.set_ylabel("median $T_{min}$, first 100 cycles (°C)")
    ax.set_title("Per-cell baseline: the batches are offset", fontsize=9)

    # row 3, panel 3: temperature rise vs the heat the policy implies
    ax = fig.add_subplot(gs[2, 2])
    for d in BATCH_DATES:
        g = tc[tc.batch_date == d]
        ax.plot(g.heat_proxy, g.T_rise_early_C, marker="o", ls="none", ms=5,
                mfc=BATCH_COLORS[d], mec="none", alpha=0.75, label=d)
    worst = tc.nsmallest(7, "T_rise_resid_C")
    for _, r in worst.iterrows():
        ax.plot(r.heat_proxy, r.T_rise_early_C, marker="o", ms=9, mfc="none",
                mec="#d03b3b", mew=1.3, zorder=5)
        ax.annotate(f"{r.batch_date[2:7]} ch{int(r.channel)}",
                    (r.heat_proxy, r.T_rise_early_C), fontsize=6.5, color=INK2,
                    xytext=(6, -2), textcoords="offset points")
    ax.set_xlabel(r"policy heat proxy $C_1 Q_1 + C_2 (80-Q_1)$")
    ax.set_ylabel(r"$T_{max}-T_{min}$, first 100 cycles (°C)")
    ax.set_title("Poor thermal contact (7 worst circled)", fontsize=9)
    ax.legend(loc="upper left", fontsize=7)

    fig.suptitle("Fig 5 — Cell temperature vs cycle (rows 1-2); chamber behaviour "
                 "and thermocouple contact (row 3)", y=0.995)
    figure_class_legend(fig, all_classes, y=0.952)
    save(fig, "fig05_temperature",
         "Rows 1-2: every cell. 2017-05-12 shows clear step changes in the whole batch at ~cycle 350, ~500 and "
         "~730-1000 — the chamber moving, not the cells. Tmax never falls below Tmin anywhere in the dataset. "
         "Row 3 left: batch-median Tavg over cycles where at least half the batch is still running. 2017-05-12 "
         "wanders 2.97 °C, the largest of the three, which is the page's 'somewhat inconsistent' temperature control "
         "— it shows up as drift over time, NOT as spread between cells (its between-cell IQR, 1.45 °C, is the "
         "batch's lowest). Row 3 middle: per-cell baseline; 2018-04-12 sits ~1.4 °C above the other two against a "
         "30 °C setpoint. Row 3 right: temperature rise against the ohmic heat each policy implies; the circled "
         "cells read far colder than their policy predicts. Only 2017-06-30 ch7 and ch21 are named on any page, and "
         "ch21 is not among them. Caveat: Tmin is a cell-surface reading, so it mixes chamber setpoint with "
         "thermocouple contact quality.", tight_rect=(0, 0.05, 1, 0.945))


# ---------------------------------------------------------------- figure 6
def fig06_capacity_artifacts():
    flags = _flags()
    sp = pd.read_csv(TABLES / "capacity_spikes.csv")
    gaps = pd.read_csv(TABLES / "time_gaps.csv")
    life = pd.read_csv(TABLES / "cycle_metrics_life.csv")
    fig = plt.figure(figsize=(14, 8.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 0.95], hspace=0.38)
    for col, d in enumerate(BATCH_DATES):
        ax = fig.add_subplot(gs[0, col])
        recs = _meta()[d]
        for r in recs:
            s, _ = _valid_summary(r)
            qd, cyc = s["QDischarge"], s["cycle"]
            st = line_style(flags[(d, r.channel)], d)
            ax.plot(cyc[1:], np.diff(qd), lw=0.5, alpha=0.35, color=st["color"])
        g = sp[sp.batch_date == d]
        ax.plot(g.cycle, g.deviation_Ah, marker="o", ls="none", ms=4.5, mfc="none",
                mec="#d03b3b", mew=1.0, zorder=5)
        gg = gaps[gaps.batch_date == d]
        ax.plot(gg.cycle, np.zeros(len(gg)), marker="|", ls="none", ms=14, mew=1.6,
                color="#6250d6", zorder=6)
        ax.set_ylim(-0.2, 0.2)
        ax.set_xlabel("cycle number")
        ax.set_title(f"{d}  ({len(recs)} cells)\n{len(g)} artifact cycles · "
                     f"{len(gg)} interrupted cycles", color=BATCH_COLORS[d], fontsize=9)
        if col == 0:
            ax.set_ylabel(r"$\Delta Q_D$ per cycle (Ah)")
        ax.legend(handles=[
            Line2D([], [], marker="o", ls="none", ms=4.5, mfc="none", mec="#d03b3b",
                   label="artifact (|dev. from rolling median| > 0.01 Ah)"),
            Line2D([], [], marker="|", ls="none", ms=12, mew=1.6, color="#6250d6",
                   label="cycle with charge time > 60 min (restart)")],
            loc="upper right")

    # bottom-left: where the artifacts sit, per batch
    ax = fig.add_subplot(gs[1, 0])
    for d in BATCH_DATES:
        g = sp[sp.batch_date == d]
        ax.hist(g.cycle, bins=np.arange(0, 1300, 25), histtype="step", lw=1.3,
                color=BATCH_COLORS[d], label=f"{d} ({len(g)})")
    ax.axvspan(240, 260, color="#6250d6", alpha=0.12, zorder=0)
    ax.annotate("cycles 240-260", xy=(250, ax.get_ylim()[1]), xytext=(430, ax.get_ylim()[1] * 0.88),
                fontsize=7, color="#6250d6",
                arrowprops=dict(arrowstyle="->", color="#6250d6", lw=0.8))
    ax.set_xlabel("cycle number"); ax.set_ylabel("artifact cycles")
    ax.set_title("Where capacity artifacts occur", fontsize=9)
    ax.legend(loc="upper right")

    # bottom-middle: the restart is one wall-clock event
    ax = fig.add_subplot(gs[1, 1])
    g = sp[(sp.batch_date == "2017-06-30") & sp.cycle.between(230, 330)]
    dur = (life[(life.batch_date == "2017-06-30") & (life.which == "cyc100")]
           .set_index("channel")["duration_min"])
    j = g.groupby("channel")["cycle"].min().to_frame("spike_cycle").join(
        dur.rename("dur")).dropna()
    ax.plot(j.dur, j.spike_cycle, marker="o", ls="none", ms=6,
            mfc=BATCH_COLORS["2017-06-30"], mec="none")
    for ch, r in j.iterrows():
        ax.annotate(f"ch{int(ch)}", (r.dur, r.spike_cycle), fontsize=6,
                    xytext=(3, 3), textcoords="offset points", color=INK2)
    rr = np.corrcoef(j.dur, j.spike_cycle)[0, 1]
    ax.set_xlabel("that cell's cycle duration at cycle 100 (min)")
    ax.set_ylabel("cycle number of its artifact")
    ax.set_title(f"2017-06-30: one wall-clock restart (r = {rr:.3f})", fontsize=9)

    # bottom-right: implied elapsed time
    ax = fig.add_subplot(gs[1, 2])
    j["elapsed_h"] = j.spike_cycle * j.dur / 60
    ax.plot(j.elapsed_h, np.arange(len(j)), marker="o", ls="none", ms=6,
            mfc=BATCH_COLORS["2017-06-30"], mec="none")
    for k, (ch, r) in enumerate(j.iterrows()):
        ax.annotate(f"ch{int(ch)}", (r.elapsed_h, k), fontsize=6, xytext=(4, -2),
                    textcoords="offset points", color=INK2)
    ax.axvspan(j.elapsed_h.min(), 255, color="#6250d6", alpha=0.12, zorder=0)
    ax.set_yticks([])
    ax.set_xlabel("implied hours since batch start at the artifact")
    ax.set_title("14 of 15 cells agree to within ~6 h", fontsize=9)

    fig.suptitle("Fig 6 — Cycle-to-cycle capacity change, artifact detection, and "
                 "the 2017-06-30 restart")
    save(fig, "fig06_capacity_artifacts",
         "Top: per-cycle change in discharge capacity for every cell (thin lines), with detected artifacts "
         "circled and cycles whose recorded charge time exceeds 60 min — direct evidence of a computer restart — "
         "ticked in violet. 2017-05-12 shows two restart events (cycle 13 and cycles 879-902, gaps of 7.0 h and "
         "~4.65 h); 2017-06-30 shows the cycle-250 event (7 cells, 8.19-8.47 h, matching the page's '8-hour rest') "
         "plus a 21.5 h gap at cycle 1000 on ch3 alone; 2018-04-12 has no cycle anywhere above 60 min. "
         "Bottom middle/right: the cycle number at which a cell shows its artifact is almost perfectly "
         "anti-correlated with that cell's cycle duration, which is what a single wall-clock interruption looks "
         "like. Note the artifacts near cycle 250 are mostly capacity DIPS, not the 'spikes' the page implies.",
         tight_rect=(0, 0.055, 1, 0.96))


if __name__ == "__main__":
    fig01_capacity_fade()
    fig02_continuations()
    fig03_cycle_life()
    fig04_internal_resistance()
    fig05_temperature()
    fig06_capacity_artifacts()
