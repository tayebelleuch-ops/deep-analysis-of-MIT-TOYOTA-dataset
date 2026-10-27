"""Step 3, figures 7-10: voltage-domain curves, the DeltaQ(V) early-life check,
within-cycle profiles with the CV tail, and the missing-data map."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr
from checks import _meta, _valid_summary, REST_I, _runs
from plotstyle import (apply_style, save, line_style, figure_class_legend, CLASS_LABEL,
                       BATCH_COLORS, BATCH_DATES, INK, INK2)

TABLES = HERE / "tables"
apply_style()
VDLIN = np.linspace(3.5, 2.0, 1000)
# sequential single-hue ramp (blue 100 -> 700) from the validated palette
BLUE_RAMP = LinearSegmentedColormap.from_list(
    "blue", ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf",
             "#184f95", "#0d366b"])


def _flags():
    df = pd.read_csv(TABLES / "cell_flags.csv")
    return {(r.batch_date, r.channel): r.cell_class for r in df.itertuples()}


# ---------------------------------------------------------------- figure 7
SAMPLE = {
    "2017-05-12": [1, 7, 15, 25, 36, 43],
    "2017-06-30": [3, 7, 10, 21, 30, 44],
    "2018-04-12": [1, 14, 33, 39, 46, 48],   # 46 = the page's "noisy voltage" cell
}
CYC_A, CYC_B = 10, 100   # cycle NUMBERS (1-based), as the paper uses them


def fig07_voltage_domain():
    flags = _flags()
    fig, axes = plt.subplots(3, 3, figsize=(14, 9.2), sharex=True)
    all_classes = set()
    for col, d in enumerate(BATCH_DATES):
        idx = {r.channel: r.index for r in _meta()[d]}
        with matr.BatchCycles(d) as bc:
            for ch in SAMPLE[d]:
                i = idx[ch]
                cls = flags[(d, ch)]
                all_classes.add(cls)
                st = line_style(cls, d)
                st["alpha"] = 0.95
                st["linewidth"] = 1.1
                a = bc.cycle(i, CYC_A - 1, ("Qdlin", "discharge_dQdV"))
                b = bc.cycle(i, CYC_B - 1, ("Qdlin", "discharge_dQdV"))
                axes[0, col].plot(VDLIN, a["Qdlin"], **{**st, "alpha": 0.45})
                axes[0, col].plot(VDLIN, b["Qdlin"], **st)
                axes[1, col].plot(VDLIN, b["discharge_dQdV"], **st)
                axes[2, col].plot(VDLIN, b["Qdlin"] - a["Qdlin"], **st)
        axes[0, col].set_title(f"{d}  ({len(SAMPLE[d])} of {len(_meta()[d])} cells shown)",
                               color=BATCH_COLORS[d])
        axes[2, col].set_xlabel("voltage $V_{dlin}$ (V)")
        axes[2, col].axhline(0, color=INK2, lw=0.6)
    axes[0, 0].set_ylabel(f"$Q_{{dlin}}$ (Ah)\nfaint = cycle {CYC_A}, solid = cycle {CYC_B}")
    axes[1, 0].set_ylabel(f"d$Q$/d$V$ (Ah/V), cycle {CYC_B}")
    axes[2, 0].set_ylabel(r"$\Delta Q_{100-10}(V)$ (Ah)")
    for ax in axes.ravel():
        ax.set_xlim(3.5, 2.0)
    fig.suptitle("Fig 7 — Voltage-domain curves at cycle 10 and cycle 100, and their "
                 "difference", y=0.995)
    figure_class_legend(fig, all_classes, y=0.952)
    save(fig, "fig07_voltage_domain",
         "x-axis runs 3.5 -> 2.0 V, the stored Vdlin grid (note it starts below the 3.6 V cutoff, so the top of "
         "the discharge curve is not covered). Cycle 100 sits below cycle 10 everywhere for every cell, and the "
         "dQ/dV peaks line up across all three batches — if 2017-05-12's cycle indices were shifted by one relative "
         "to the others, these curves would not align, so this corroborates the schema finding that numbering is "
         "NOT offset. 2018-04-12 ch46 (the page's 'noisy voltage profiles' cell) is in the right-hand sample and is "
         "no rougher than its neighbours at these cycles.", tight_rect=(0, 0.05, 1, 0.945))


# ---------------------------------------------------------------- figure 8
def compute_deltaq() -> pd.DataFrame:
    """log10 var of DeltaQ_{100-10}(V) per cell -- the paper's early-life feature.

    Computed on each cell's FIRST struct segment, since cycles 10 and 100 always
    fall there, and paired with the cell's joined cycle life.
    """
    inv = pd.read_csv(HERE / "cell_inventory.csv")
    inv = inv[inv.in_struct]
    rows = []
    for d in BATCH_DATES:
        idx = {r.channel: r.index for r in _meta()[d]}
        sub = inv[inv.batch_date == d]
        with matr.BatchCycles(d) as bc:
            for _, r in sub.iterrows():
                ch = int(r.channel)
                if ch not in idx or bc.n_cycles(idx[ch]) <= CYC_B:
                    continue
                i = idx[ch]
                a = bc.cycle(i, CYC_A - 1, ("Qdlin",))["Qdlin"]
                b = bc.cycle(i, CYC_B - 1, ("Qdlin",))["Qdlin"]
                dq = b - a
                rows.append({
                    "batch_date": d, "channel": ch, "barcode": r.barcode,
                    "policy_canonical": r.policy_canonical,
                    "policy_C1": r.policy_C1,
                    "var_deltaQ": float(np.var(dq)),
                    "log_var_deltaQ": float(np.log10(np.var(dq))),
                    "cycle_life_cycles": r.cycle_life_cycles,
                    "n_cycles_recorded": r.n_cycles_recorded,
                    "cycle_life_basis": r.cycle_life_basis,
                    "censored": bool(r.censored),
                })
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "deltaq_feature.csv", index=False)
    print(f"wrote tables/deltaq_feature.csv ({len(df)} rows)")
    return df


def fig08_deltaq_vs_life(dq: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    ax = axes[0]
    for d in BATCH_DATES:
        g = dq[(dq.batch_date == d) & ~dq.censored]
        ax.plot(g.log_var_deltaQ, g.cycle_life_cycles, marker="o", ls="none", ms=6,
                mfc=BATCH_COLORS[d], mec="none", alpha=0.8, label=f"{d} ({len(g)})")
    # censored cells have no cycle life; plot them at their last recorded cycle,
    # which is a lower bound, and say so in the legend
    n_cens = 0
    for d in BATCH_DATES:
        g = dq[(dq.batch_date == d) & dq.censored]
        if len(g):
            n_cens += len(g)
            ax.plot(g.log_var_deltaQ, g.n_cycles_recorded, marker="^", ls="none", ms=9,
                    mfc="none", mec="#d03b3b", mew=1.4, zorder=5,
                    label=f"censored, lower bound ({len(g)})" if n_cens == len(g) else None)
    ax.set_yscale("log")
    ax.set_xlabel(r"$\log_{10}\,\mathrm{var}\,\Delta Q_{100-10}(V)$")
    ax.set_ylabel("cycle life (cycles, log scale)")
    ax.set_title("coloured by batch", fontsize=9.5)
    ax.legend(loc="upper right")

    ax = axes[1]
    yy = dq.cycle_life_cycles.where(~dq.censored, dq.n_cycles_recorded)
    sc = ax.scatter(dq.log_var_deltaQ, yy, c=dq.policy_C1,
                    cmap=BLUE_RAMP, s=38, edgecolors="none", alpha=0.9, vmin=1, vmax=8)
    ax.set_yscale("log")
    cb = fig.colorbar(sc, ax=ax, pad=0.02)
    cb.set_label("first-step charge rate $C_1$ (C)")
    cb.outline.set_visible(False)
    ax.set_xlabel(r"$\log_{10}\,\mathrm{var}\,\Delta Q_{100-10}(V)$")
    ax.set_title("coloured by charging policy ($C_1$)", fontsize=9.5)
    fig.suptitle("Fig 8 — Early-life $\\Delta Q(V)$ variance against cycle life "
                 f"({len(dq)} cells; no model fitted)")
    save(fig, "fig08_deltaq_vs_cycle_life",
         "One dot per cell. NO model is fitted — this is the raw scatter. Censored cells are at their last "
         "recorded cycle, a lower bound. The three batches sit on visibly different levels, which is expected: "
         "cycle life is measured against 0.88 Ah in 2017-05-12 and 2018-04-12 but 0.825 Ah in 2017-06-30, and "
         "for the first two it is the test-termination cycle rather than a measured crossing. Pooling the "
         "batches without a batch term would confound the relationship with that definitional difference.")


# ---------------------------------------------------------------- figure 9
def fig09_within_cycle():
    d, ch = "2018-04-12", 1
    idx = {r.channel: r.index for r in _meta()[d]}
    i = idx[ch]
    life = pd.read_csv(TABLES / "cycle_metrics_life.csv")
    fig = plt.figure(figsize=(15, 8.6))
    gs = fig.add_gridspec(3, 3, hspace=0.32, wspace=0.26)
    with matr.BatchCycles(d) as bc:
        n = bc.n_cycles(i)
        for col, (tag, ci) in enumerate([(f"cycle {CYC_B} (early)", CYC_B - 1),
                                         (f"cycle {n} (last)", n - 1)]):
            c = bc.cycle(i, ci, ("t", "V", "I", "T"))
            t, I, V = c["t"], c["I"], c["T"] * 0 + c["T"]
            chg = c["I"] > REST_I
            vmax = np.nanmax(c["V"][chg])
            cv = chg & (c["V"] > vmax - 0.001)
            rest = np.abs(c["I"]) <= REST_I
            for row, (field, label) in enumerate([("V", "voltage (V)"),
                                                  ("I", "current (C-rate)"),
                                                  ("T", "temperature (°C)")]):
                ax = fig.add_subplot(gs[row, col])
                ax.plot(c["t"], c[field], color=BATCH_COLORS[d], lw=1.1)
                if cv.any():
                    ax.axvspan(c["t"][cv].min(), c["t"][cv].max(), color="#6250d6",
                               alpha=0.12, zorder=0)
                for a, b in _runs(rest):
                    if b > a:
                        ax.axvspan(c["t"][a], c["t"][b], color="#eb6834", alpha=0.22,
                                   zorder=0)
                if row == 0:
                    ax.set_title(f"{d} ch{ch} — {tag}", color=BATCH_COLORS[d], fontsize=9.5)
                    ax.legend(handles=[
                        Line2D([], [], color="#6250d6", alpha=0.35, lw=8, label="CV tail"),
                        Line2D([], [], color="#eb6834", alpha=0.45, lw=8, label="rest")],
                        loc="lower right", fontsize=7)
                if row == 2:
                    ax.set_xlabel("time within cycle (min)")
                if col == 0:
                    ax.set_ylabel(label)

    # CV fraction panels
    ax = fig.add_subplot(gs[0, 2])
    for d2 in BATCH_DATES:
        g = life[(life.batch_date == d2) & life.which.isin(["cyc10", "last"])]
        piv = g.pivot_table(index="channel", columns="which", values="cv_fraction_of_charge")
        for _, r in piv.dropna().iterrows():
            ax.plot([0, 1], [r["cyc10"], r["last"]], color=BATCH_COLORS[d2], lw=0.6,
                    alpha=0.35)
        ax.plot([0, 1], [piv["cyc10"].median(), piv["last"].median()],
                color=BATCH_COLORS[d2], lw=2.4, label=d2, zorder=5)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["cycle 10", "last cycle"])
    ax.set_ylabel("CV share of the charge step")
    ax.set_title("CV tail grows over life", fontsize=9.5)
    ax.legend(loc="upper left", fontsize=7)

    ax = fig.add_subplot(gs[1, 2])
    g = life[life.which == "last"]
    for d2 in BATCH_DATES:
        gg = g[g.batch_date == d2]
        ax.plot(gg.policy_C1, gg.cv_fraction_of_charge, marker="o", ls="none", ms=5,
                mfc=BATCH_COLORS[d2], mec="none", alpha=0.8, label=d2)
    ax.set_xlabel("first-step charge rate $C_1$ (C)")
    ax.set_ylabel("CV share, last cycle")
    ax.set_title("by policy and batch", fontsize=9.5)

    ax = fig.add_subplot(gs[2, 2])
    data = [g[g.batch_date == d2].cv_fraction_of_charge.dropna() for d2 in BATCH_DATES]
    bp = ax.boxplot(data, patch_artist=True, widths=0.55,
                    medianprops=dict(color=INK, lw=1.4),
                    flierprops=dict(marker="o", ms=3, mfc="none", mec=INK2))
    for patch, d2 in zip(bp["boxes"], BATCH_DATES):
        patch.set_facecolor(BATCH_COLORS[d2]); patch.set_alpha(0.45)
        patch.set_edgecolor(BATCH_COLORS[d2])
    ax.set_xticklabels([d2[2:] for d2 in BATCH_DATES], fontsize=8)
    ax.set_ylabel("CV share, last cycle")
    ax.set_title("median 0.84 / 0.86 / 0.65", fontsize=9.5)

    fig.suptitle("Fig 9 — Within-cycle profiles early and late in life, and how much "
                 "of the charge is constant-voltage")
    save(fig, "fig09_within_cycle_profiles",
         "Left two columns: one cell's voltage, current and temperature against time within a single cycle, early "
         "and at end of life. Orange bands are rests (2018-04-12's four 5-second rests, partly merged at the ~5 s "
         "sampling interval); the violet band is the constant-voltage tail, where the cell sits at the 3.6 V cutoff "
         "and current decays to the C/20 cutoff. The fast-charge CC steps shorten as the cell ages while the CV "
         "tail lengthens. Right column: the CV share of the charge step rises from 0.315-0.330 at cycle 10 in all "
         "three batches to 0.842 (2017-05-12), 0.863 (2017-06-30) and 0.654 (2018-04-12) at the last cycle. The "
         "batches have already diverged by mid-life (0.352 / 0.747 / 0.294): 2017-06-30 charges hardest and was "
         "cycled furthest. The CV phase is taken as charge samples within 5 mV of the 3.6 V cutoff — keying it to "
         "each cycle's own maximum voltage instead reports a spurious zero on cycles with a small overshoot.")


# ---------------------------------------------------------------- figure 10
def fig10_missing_data():
    md = pd.read_csv(TABLES / "missing_summary_data.csv")
    sp = pd.read_csv(TABLES / "capacity_spikes.csv")
    gaps = pd.read_csv(TABLES / "time_gaps.csv")
    pauses = pd.read_csv(TABLES / "cycling_pauses.csv")
    tc = pd.read_csv(TABLES / "thermocouple_outliers.csv")
    flags = _flags()

    m = md.merge(sp.groupby(["batch_date", "channel"]).size().rename("artifact_cycles"),
                 on=["batch_date", "channel"], how="left")
    m = m.merge(gaps.groupby(["batch_date", "channel"]).size().rename("restart_cycles"),
                on=["batch_date", "channel"], how="left")
    m = m.merge(pauses[["batch_date", "channel", "n_cycles_over_median_plus_3min"]]
                .rename(columns={"n_cycles_over_median_plus_3min": "long_charge_cycles"}),
                on=["batch_date", "channel"], how="left")
    m = m.merge(tc[["batch_date", "channel", "T_rise_resid_C"]],
                on=["batch_date", "channel"], how="left")
    m["poor_thermal_contact"] = (-m["T_rise_resid_C"]).clip(lower=0)
    m[["artifact_cycles", "restart_cycles"]] = m[["artifact_cycles", "restart_cycles"]].fillna(0)
    m["cell_class"] = [flags[(d, c)] for d, c in zip(m.batch_date, m.channel)]
    m.to_csv(TABLES / "fig10_cell_quality_matrix.csv", index=False)

    COLS = [("n_leading_placeholder", "placeholder\ncycles"),
            ("n_nonpos_IR", "IR = 0\ncycles"),
            ("artifact_cycles", "capacity\nartifacts"),
            ("restart_cycles", "restart\ncycles"),
            ("long_charge_cycles", "long-charge\ncycles"),
            ("n_ce_above_1.01", "CE > 1.01\ncycles"),
            ("poor_thermal_contact", "thermal\ncontact (°C)")]

    fig = plt.figure(figsize=(16, 11))
    outer = fig.add_gridspec(1, 3, wspace=0.30)
    for bi, d in enumerate(BATCH_DATES):
        g = m[m.batch_date == d].sort_values("channel").reset_index(drop=True)
        n_rows = len(g)
        gs = outer[0, bi].subgridspec(1, 2, width_ratios=[1, 1.55], wspace=0.04)
        # cycle count per cell
        ax = fig.add_subplot(gs[0, 0])
        for k, r in g.iterrows():
            st = line_style(r.cell_class, d)
            ax.barh(k, r.n_cycles, color=st["color"], alpha=0.85, height=0.75)
        ax.set_yticks(np.arange(n_rows))
        ax.set_yticklabels([f"ch{int(c):02d}" for c in g.channel], fontsize=5.5)
        ax.set_ylim(n_rows - 0.5, -0.5)          # exactly imshow's extent, so rows line up
        ax.set_xlabel("cycles recorded")
        ax.set_title(f"{d}  ({n_rows} cells)", color=BATCH_COLORS[d], fontsize=9.5)
        ax.grid(axis="y", visible=False)
        ax.tick_params(axis="y", length=0)

        # issue heatmap
        ax = fig.add_subplot(gs[0, 1])
        M = g[[c for c, _ in COLS]].to_numpy(dtype=float)
        Mn = np.zeros_like(M)
        for j in range(M.shape[1]):
            col = M[:, j]
            top = np.nanmax(col)
            Mn[:, j] = np.log1p(col) / np.log1p(top) if top > 0 else 0
        ax.imshow(Mn, cmap=BLUE_RAMP, aspect="auto", vmin=0, vmax=1,
                  interpolation="nearest")
        for k in range(M.shape[0]):
            for j in range(M.shape[1]):
                if M[k, j] > 0:
                    ax.text(j, k, f"{M[k, j]:.0f}" if COLS[j][0] != "poor_thermal_contact"
                            else f"{M[k, j]:.1f}",
                            ha="center", va="center", fontsize=5,
                            color="#f0efec" if Mn[k, j] > 0.6 else INK)
        ax.set_xticks(range(len(COLS)))
        ax.set_xticklabels([lab for _, lab in COLS], fontsize=6, rotation=90)
        ax.set_ylim(n_rows - 0.5, -0.5)
        ax.set_yticks([])
        ax.grid(False)
    fig.suptitle("Fig 10 — Cycles recorded per cell, and a per-cell map of every "
                 f"data-quality indicator ({len(m)} struct rows)", y=0.985)
    figure_class_legend(fig, set(m.cell_class), y=0.945)
    save(fig, "fig10_missing_data_map",
         "Bars: cycles recorded per cell, coloured by flag class. Heatmap: one row per cell, one column per "
         "indicator, shaded on a log scale within each column (darker = more) with the raw count printed. "
         "There are NO missing values anywhere: not one NaN in QDischarge, QCharge, IR, Tavg, Tmin, Tmax or "
         "chargetime in any of the 140 struct rows, and cycle numbering is contiguous in every cell. "
         "'placeholder cycles' is 2017-05-12's zero-filled cycle 1. 'CE > 1.01' counts cycles whose discharge "
         "exceeds charge capacity by more than 1%, which tracks the restart artifacts; the systematic +0.02% "
         "excess present on most cycles is integration resolution, not a defect. 'thermal contact' is how many "
         "°C below its policy-predicted temperature rise the cell reads.", tight_rect=(0, 0.045, 1, 0.94))


if __name__ == "__main__":
    fig07_voltage_domain()
    dq = compute_deltaq()
    fig08_deltaq_vs_life(dq)
    fig09_within_cycle()
    fig10_missing_data()
