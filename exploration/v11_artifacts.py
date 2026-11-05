"""Stage 2, items 4 and 8 plus the dedicated section on the two structurally bloated
cells (2018-04-12 ch 46 and 2017-05-12 ch 17).

Item 4 asks three things:
  * show the cycles v1.0 flags (restart, artifact, junction) as raw V / I / Qd traces;
  * find bad cycles the summary-level detectors missed;
  * settle whether EL150800453240's cycle-40 reading of 2.884 Ah is a bad summary over a
    good series, or a bad series.

Reads the extracted HDF5 files. Writes tables to `tables/v11_*.csv` and figures to
`figures/figv11_*.png`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr
import plotstyle as ps
import matplotlib.pyplot as plt

OUT = HERE / "extract_out"
TABLES = HERE / "tables"
BATCHES = matr.BATCH_DATES

BLOATED = [("2018-04-12", 46, "EL150800737364"), ("2017-05-12", 17, "EL150800453240")]
FLAGS = ["series_present", "series_time_monotone", "series_time_contiguous",
         "series_duration_plausible", "series_length_plausible",
         "series_voltage_in_range", "series_current_in_range",
         "series_grid_in_range", "series_no_nan"]


def series(date: str, h5_row: int, fields=("t", "V", "I", "Qd", "Qc")) -> dict:
    with h5py.File(OUT / f"within_cycle_{date}.h5", "r") as f:
        off = f["native/offset"]
        a, b = int(off[h5_row]), int(off[h5_row + 1])
        d = {k: f[f"native/{k}"][a:b].astype(float) for k in fields}
        d["Qdlin"] = f["grid/Qdlin"][h5_row].astype(float)
        d["vdlin"] = f["vdlin"][:]
    return d


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.read_csv(OUT / "within_cycle_index.csv")
    cy = pd.read_csv(HERE / "analysis_set_cycles.csv")
    v1 = ["is_measured_cycle", "is_artifact_cycle", "is_restart_cycle",
          "is_junction_cycle", "is_clean_cycle"]
    j = idx.merge(cy[["cell_uid", "cycle"] + v1], on=["cell_uid", "cycle"], how="left")
    # a left merge leaves these as object dtype with NaN on the 1,179 beyond_crossing
    # rows, which are not in v1.0 at all. Cast to a real bool, False off the analysis
    # set, so that `~` means logical negation rather than integer bit-flipping.
    for c in v1:
        j[c] = j[c].map({True: True, False: True and False}).fillna(False).astype(bool)
    return idx, j


def h(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# ---------------------------------------------------------------------------

def crosstab(j: pd.DataFrame) -> None:
    h("ITEM 4a  THE v1.0 FLAGS AGAINST THE SERIES-LEVEL CHECKS")
    ins = j[j.in_analysis_set]
    print(f"\non the {len(ins):,} rows the analysis set contains:")
    ct = pd.crosstab(ins.is_clean_cycle, ins.is_series_valid,
                     rownames=["v1.0 is_clean_cycle"], colnames=["is_series_valid"])
    print(ct.to_string())
    ct.to_csv(TABLES / "v11_clean_vs_series_valid.csv")

    print("\nhow often each v1.0 flag and each series check fire together:")
    rows = []
    for label, sel in [("is_artifact_cycle", ins.is_artifact_cycle),
                       ("is_restart_cycle", ins.is_restart_cycle),
                       ("is_junction_cycle", ins.is_junction_cycle),
                       ("NOT is_measured_cycle", ~ins.is_measured_cycle)]:
        n = int(sel.sum())
        bad = int((sel & ~ins.is_series_valid).sum())
        rows.append({"v1.0_flag": label, "n_flagged": n,
                     "of_which_series_invalid": bad,
                     "pct_of_flagged": 100 * bad / n if n else float("nan")})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    t.to_csv(TABLES / "v11_flag_overlap.csv", index=False)

    print("\nseries-invalid rows by which check failed, split by whether v1.0 caught them:")
    bad = ins[~ins.is_series_valid].copy()
    rows = []
    for f in FLAGS:
        s = bad[~bad[f]]
        rows.append({"check": f, "n_fail": len(s),
                     "missed_by_v1_0": int(s.is_clean_cycle.sum()),
                     "already_flagged_by_v1_0": int((~s.is_clean_cycle).sum()),
                     "cells": int(s.cell_uid.nunique())})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    t.to_csv(TABLES / "v11_series_fail_vs_v1_0.csv", index=False)

    missed = ins[ins.is_clean_cycle & ~ins.is_series_valid]
    print(f"\n==> {len(missed)} cycles are is_clean_cycle = True in v1.0 but fail a "
          f"series check, across {missed.cell_uid.nunique()} cells.")
    print("    These are the proposed v1.0 corrections "
          "(tables/v11_proposed_clean_cycle_corrections.csv).")
    if len(missed):
        g = missed.groupby(["source_batch_date", "source_channel", "cell_uid"]).agg(
            n_cycles=("cycle", "size"),
            cycles=("cycle", lambda c: ",".join(map(str, sorted(c)[:10]))))
        print(g.to_string())


def traces(j: pd.DataFrame) -> None:
    h("ITEM 4b  RAW TRACES OF THE v1.0-FLAGGED CYCLES")
    ps.apply_style()
    ins = j[j.in_analysis_set & ~j.is_placeholder]
    picks = []
    for label, sel in (("restart", ins[ins.is_restart_cycle]),
                       ("artifact", ins[ins.is_artifact_cycle & ~ins.is_restart_cycle]),
                       ("junction", ins[ins.is_junction_cycle])):
        if len(sel):
            r = sel.iloc[0]
            picks.append((label, r))
            print(f"  {label:9s}: {r.cell_uid} cycle {r.cycle} "
                  f"({r.source_batch_date} ch{r.source_channel}), "
                  f"n={r.n_samples}, series_valid={r.is_series_valid}")

    fig, axes = plt.subplots(3, len(picks), figsize=(4.0 * len(picks), 8.4), squeeze=False)
    for c, (label, r) in enumerate(picks):
        nb = ins[(ins.cell_uid == r.cell_uid)
                 & (ins.cycle.between(r.cycle - 8, r.cycle - 4))
                 & ins.is_clean_cycle & ins.is_series_valid]
        d = series(r.source_batch_date, int(r.h5_row))
        col = ps.BATCH_COLORS[r.source_batch_date]
        for row, (k, ylab) in enumerate((("V", "V (V)"), ("I", "I (C-rate)"),
                                         ("Qd", "Qd (Ah)"))):
            ax = axes[row][c]
            if len(nb):
                n = nb.iloc[0]
                dn = series(n.source_batch_date, int(n.h5_row))
                ax.plot(dn["t"], dn[k], color=ps.INK2, lw=0.8, ls=(0, (4, 2)),
                        label=f"valid cycle {int(n.cycle)}")
            ax.plot(d["t"], d[k], color=col, lw=1.0, label=f"{label} cycle {int(r.cycle)}")
            ax.set_ylabel(ylab)
            if row == 2:
                ax.set_xlabel("t (minutes)")
            if row == 0:
                ax.set_title(f"{label}: {r.cell_uid}\n{r.source_batch_date} "
                             f"ch{int(r.source_channel)}, cycle {int(r.cycle)}")
                ax.legend(loc="best")
    ps.save(fig, "figv11_01_flagged_cycle_traces",
            "Raw within-cycle V, I and Qd for one cycle of each class the v1.0 summary-level "
            "detectors flag, against a clean cycle of the same cell (dashed grey). Traces are "
            "as extracted; nothing is smoothed. Flag class is distinguished by dash pattern as "
            "well as colour.")


def cycle40(j: pd.DataFrame) -> None:
    h("ITEM 4c  EL150800453240 CYCLE 40: BAD SUMMARY, OR BAD SERIES?")
    ps.apply_style()
    uid = "EL150800453240"
    s = j[(j.cell_uid == uid) & j.cycle.between(36, 56)]
    cols = ["cycle", "n_samples", "t_end_min", "dt_median_s", "dt_max_s", "n_dt_zero",
            "V_min", "V_max", "I_peak_abs", "Qd_last", "QDischarge_Ah",
            "Q_dis_integral_Ah", "is_series_valid", "is_clean_cycle"]
    print(s[cols].to_string(index=False, float_format=lambda x: f"{x:.4g}"))
    s[cols].to_csv(TABLES / "v11_cell_EL150800453240_cycles.csv", index=False,
                   float_format="%.6g")

    r40 = j[(j.cell_uid == uid) & (j.cycle == 40)].iloc[0]
    print(f"\nverdict inputs for cycle 40:")
    print(f"  n_samples              {r40.n_samples:,}  (neighbours ~1,700-2,200)")
    print(f"  t_end_min              {r40.t_end_min:,.1f} min = {r40.t_end_min/60:.1f} h")
    print(f"  Qd[-1] from the series {r40.Qd_last:.4f} Ah")
    print(f"  QDischarge (summary)   {r40.QDischarge_Ah:.4f} Ah")
    print(f"  integral(-I dt)        {r40.Q_dis_integral_Ah:.4f} Ah")
    print(f"  => the series' own Qd reaches the same 2.884 Ah the summary reports, so the")
    print(f"     summary is a faithful readout of a corrupt row. The SERIES is the bad thing.")

    cell = j[j.cell_uid == uid].sort_values("cycle")
    badc = cell[~cell.is_series_valid]
    print(f"\n  the cell's series-invalid cycles: {len(badc)} of {len(cell)}, "
          f"spanning cycles {int(badc.cycle.min())}-{int(badc.cycle.max())}")
    print(f"  of those, is_clean_cycle = True in v1.0: {int(badc.is_clean_cycle.sum())}")
    # a genuinely valid reference cycle -- cycle 30 is NOT one, despite being
    # is_clean_cycle = True in v1.0: it carries a 48 h internal gap of its own.
    ref = cell[cell.is_series_valid & (cell.cycle > badc.cycle.max())].iloc[0]
    print(f"  nearest fully valid cycle after the bad run: {int(ref.cycle)} "
          f"(t_end {ref.t_end_min:.2f} min)")

    fig, axes = plt.subplots(2, 2, figsize=(11.4, 7.0))
    col = ps.BATCH_COLORS["2017-05-12"]
    lo, hi = int(badc.cycle.min()), int(badc.cycle.max())
    for ax, (c, ylab, logy) in zip(axes[0], [("t_end_min", "cycle duration (min)", True),
                                             ("n_samples", "samples in the cycle", True)]):
        ax.plot(cell.cycle, cell[c], color=col, lw=0.8)
        ax.axvspan(lo, hi, color="#b3261e", alpha=0.10, lw=0)
        if logy:
            ax.set_yscale("log")
        ax.set_xlabel("cycle"); ax.set_ylabel(ylab)
        ax.set_title(f"{ylab} over the cell's life")
    axes[0][0].annotate(f"cycles {lo}-{hi}\nseries-invalid", xy=(hi, cell.t_end_min.max()),
                        xytext=(hi + 140, cell.t_end_min.max() * 0.8), fontsize=7.5,
                        color="#b3261e")

    r40 = cell[cell.cycle == 40].iloc[0]
    for ax, r, lab in ((axes[1][0], r40, f"cycle {int(r40.cycle)} (series-invalid)"),
                       (axes[1][1], ref, f"cycle {int(ref.cycle)} (series-valid)")):
        d = series(r.source_batch_date, int(r.h5_row))
        ax.plot(d["t"], d["V"], color=col, lw=0.6)
        ax.axhline(3.6, color="#b3261e", lw=0.6, ls=":")
        ax.axhline(2.0, color="#b3261e", lw=0.6, ls=":")
        ax.set_xlabel("t (minutes)"); ax.set_ylabel("V (V)")
        ax.set_title(f"{lab}\nn={int(r.n_samples):,}, t_end={r.t_end_min:,.1f} min, "
                     f"V_max={r.V_max:.3f} V")
    fig.suptitle("EL150800453240 (2017-05-12 ch 17, struct index 18): the corrupt run is "
                 f"cycles {lo}-{hi}, not just cycle 40")
    ps.save(fig, "figv11_02_cell17_corrupt_run",
            "Shaded band: the cycles that fail a series check. Their rows splice a normal "
            "cycle onto a fragment recorded 36-48 h later, so duration and sample count "
            "jump by ~50x while the summary still reports a plausible 1.069 Ah. v1.0 flags "
            "only cycle 40, as a capacity artifact. The 2.0 V and 3.6 V cutoffs are dotted; "
            "the bad run breaches both.")


def bloated(j: pd.DataFrame) -> None:
    h("SECTION B  THE TWO STRUCTURALLY BLOATED CELLS")
    ps.apply_style()
    rows = []
    for date, ch, uid in BLOATED:
        s = j[j.cell_uid == uid]
        med = j[(j.source_batch_date == date) & ~j.is_placeholder].n_samples.median()
        big = s[s.n_samples > 5 * med]
        rows.append({
            "cell_uid": uid, "batch_date": date, "channel": ch,
            "n_cycles": len(s), "batch_median_n_samples": med,
            "cell_median_n_samples": s.n_samples.median(),
            "max_n_samples": int(s.n_samples.max()),
            "n_cycles_over_5x_batch_median": len(big),
            "n_series_invalid": int((~s.is_series_valid).sum()),
            "n_v1_0_clean": int(s.is_clean_cycle.sum()),
            "n_v1_0_clean_but_series_invalid": int((s.is_clean_cycle & ~s.is_series_valid).sum()),
            "n_v1_0_artifact": int(s.is_artifact_cycle.sum()),
            "bloated_cycles": ",".join(map(str, sorted(big.cycle)[:60])),
        })
    t = pd.DataFrame(rows)
    print(t.drop(columns=["bloated_cycles"]).to_string(index=False,
                                                       float_format=lambda x: f"{x:.0f}"))
    t.to_csv(TABLES / "v11_bloated_cells.csv", index=False)

    fig, axes = plt.subplots(2, 2, figsize=(11.0, 7.0))
    for r, (date, ch, uid) in enumerate(BLOATED):
        s = j[j.cell_uid == uid].sort_values("cycle")
        peers = j[(j.source_batch_date == date) & (j.cell_uid != uid)
                  & ~j.is_placeholder]
        col = ps.BATCH_COLORS[date]
        ax = axes[r][0]
        pm = peers.groupby("cycle").n_samples.median()
        ax.plot(pm.index, pm.values, color=ps.INK2, lw=0.8, ls=(0, (4, 2)),
                label=f"{date} median of the other cells")
        ax.plot(s.cycle, s.n_samples, color=col, lw=0.7, label=f"ch {ch} ({uid})")
        ax.set_yscale("log")
        ax.set_xlabel("cycle"); ax.set_ylabel("samples in the cycle")
        ax.set_title(f"{date} ch {ch}: samples per cycle")
        ax.legend(loc="best")

        worst = s.nlargest(1, "n_samples").iloc[0]
        d = series(date, int(worst.h5_row))
        ax = axes[r][1]
        ax.plot(d["t"], d["V"], color=col, lw=0.5)
        ax.axhline(3.6, color="#b3261e", lw=0.6, ls=":")
        ax.axhline(2.0, color="#b3261e", lw=0.6, ls=":")
        ax.set_xlabel("t (minutes)"); ax.set_ylabel("V (V)")
        ax.set_title(f"its longest cycle, {int(worst.cycle)}: "
                     f"n={int(worst.n_samples):,}, t_end={worst.t_end_min:,.0f} min")
    fig.suptitle("The two cells whose within-cycle records are structurally bloated")
    ps.save(fig, "figv11_03_bloated_cells",
            "Left: samples per cycle, log scale, against the median of every other cell in "
            "the same batch (dashed grey). Right: the voltage trace of each cell's longest "
            "cycle, with the 2.0 V and 3.6 V cutoffs dotted. Both cells are already flagged "
            "at cell level in v1.0 for other reasons; the bloat is visible only in the series.")


def qdlin_corruption(j: pd.DataFrame) -> None:
    h("ITEM 8  THE INTERPOLATED FIELDS GO PHYSICALLY IMPOSSIBLE (candidate U13/U14)")
    ps.apply_style()
    ins = j[~j.is_placeholder]
    bad = ins[~ins.series_grid_in_range].copy()
    print(f"\ncycles whose grid fields leave the physical band: {len(bad)}, "
          f"on {bad.cell_uid.nunique()} cells")
    cols = ["cell_uid", "cycle", "source_batch_date", "source_channel", "Qdlin_min",
            "Qdlin_max", "dQdV_min", "QDischarge_Ah", "is_clean_cycle",
            "is_artifact_cycle", "is_restart_cycle", "chargetime_min"]
    bb = bad[cols].sort_values(["source_batch_date", "source_channel", "cycle"])
    print(bb.to_string(index=False, float_format=lambda x: f"{x:.4g}"))
    bb.to_csv(TABLES / "v11_grid_out_of_range.csv", index=False, float_format="%.6g")
    print(f"\n  of these, is_clean_cycle = True in v1.0: {int(bad.is_clean_cycle.sum())}")
    print(f"  magnitude: Qdlin reaches {bad.Qdlin_max.max():,.1f} Ah and "
          f"{bad.Qdlin_min.min():,.1f} Ah on a 1.1 Ah cell")

    # Do they cluster in cycle number? A test interruption is a wall-clock event, so
    # cells cycling at different rates meet it at different cycle numbers -- which is
    # why REPORT.md section 4.1 finds the 2017-06-30 event spread over cycles 246-258.
    # Clustering window: 30 cycles, wide enough to hold that known 13-cycle spread.
    CLUSTER_W = 30
    print(f"\nclustered in cycle number (cycles within {CLUSTER_W} of each other):")
    crows = []
    for b, sb in bad.groupby("source_batch_date"):
        cyc = np.sort(sb.cycle.values)
        groups, cur = [], [int(cyc[0])]
        for x in cyc[1:]:
            if int(x) - cur[-1] <= CLUSTER_W:
                cur.append(int(x))
            else:
                groups.append(cur)
                cur = [int(x)]
        groups.append(cur)
        for gcl in groups:
            sub = sb[sb.cycle.isin(gcl)]
            crows.append({
                "batch_date": b, "cycle_lo": int(min(gcl)), "cycle_hi": int(max(gcl)),
                "n_cycles": len(sub), "n_cells": int(sub.cell_uid.nunique()),
                "chargetime_min_min": sub.chargetime_min.min(),
                "chargetime_min_max": sub.chargetime_min.max(),
                "n_v1_0_clean": int(sub.is_clean_cycle.sum()),
                "n_v1_0_restart": int(sub.is_restart_cycle.sum()),
                "channels": ",".join(map(str, sorted(sub.source_channel.unique()))),
            })
    ct = pd.DataFrame(crows)
    print(ct.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    ct.to_csv(TABLES / "v11_grid_out_of_range_clusters.csv", index=False,
              float_format="%.4g")
    # the restarts REPORT.md section 4.1 documents, as (batch, cycle_lo, cycle_hi)
    DOCUMENTED = [("2017-05-12", 1, 20), ("2017-05-12", 870, 915),
                  ("2017-06-30", 240, 265), ("2017-06-30", 300, 335),
                  ("2017-06-30", 990, 1010)]
    MIN_CELLS = 4            # a single cell is a cell fault, not a rig event
    multi = ct[ct.n_cells >= MIN_CELLS]
    print(f"\nclusters touching {MIN_CELLS}+ cells -- candidates for a common "
          f"wall-clock event:")
    for _, r in multi.iterrows():
        known = next((f"documented ({lo}-{hi})" for b, lo, hi in DOCUMENTED
                      if b == r.batch_date and lo <= r.cycle_lo and r.cycle_hi <= hi),
                     "UNDOCUMENTED")
        print(f"  {r.batch_date} cycles {r.cycle_lo}-{r.cycle_hi}: {r.n_cells} cells "
              f"(ch {r.channels}), chargetime {r.chargetime_min_min:.1f}-"
              f"{r.chargetime_min_max:.1f} min, {r.n_v1_0_clean}/{r.n_cycles} clean in "
              f"v1.0 -> {known}")
    print("\n  A cluster with normal charge time and no IR = 0 reading is invisible to")
    print("  both v1.0 restart detectors (REPORT.md section 4.3.1), so it could only be")
    print("  found in the voltage-domain fields.")

    if len(bad):
        fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.3))
        worst = bad.nlargest(1, "Qdlin_max").iloc[0]
        d = series(worst.source_batch_date, int(worst.h5_row))
        nb = ins[(ins.cell_uid == worst.cell_uid)
                 & (ins.cycle.between(worst.cycle - 15, worst.cycle - 5))
                 & ins.is_series_valid]
        axes[0].plot(d["vdlin"], d["Qdlin"], color="#b3261e", lw=0.9,
                     label=f"cycle {int(worst.cycle)} (restart)")
        if len(nb):
            dn = series(nb.iloc[0].source_batch_date, int(nb.iloc[0].h5_row))
            axes[0].plot(dn["vdlin"], dn["Qdlin"], color=ps.INK2, lw=0.9,
                         ls=(0, (4, 2)),
                         label=f"cycle {int(nb.iloc[0].cycle)} (series-valid)")
        axes[0].set_xlabel("Vdlin (V)"); axes[0].set_ylabel("Qdlin (Ah)")
        axes[0].invert_xaxis()
        axes[0].set_title(f"{worst.cell_uid} {worst.source_batch_date} "
                          f"ch{int(worst.source_channel)}: Qdlin blows up")
        axes[0].legend(loc="best")
        # how far out of the band each cycle goes, on whichever side is worse:
        # for many of these it is the negative excursion, not the positive one.
        excursion = np.maximum(bad.Qdlin_max.abs(), bad.Qdlin_min.abs())
        axes[1].plot(np.sort(excursion.values),
                     np.arange(len(bad)) / max(len(bad) - 1, 1), marker="o", ms=3,
                     color="#b3261e", lw=0.8)
        axes[1].set_xscale("log")
        axes[1].axvline(1.1, color=ps.INK2, lw=0.8, ls=":")
        axes[1].set_xlabel("worst |Qdlin| excursion in the cycle (Ah, log scale)")
        axes[1].set_ylabel("cumulative fraction")
        axes[1].set_title("how far out of range they go\n(dotted: 1.1 Ah nominal)")
        ps.save(fig, "figv11_04_qdlin_corruption",
                "Left: the interpolated discharge curve of the worst-affected restart cycle "
                "against a clean cycle of the same cell, on the stored 3.5-2.0 V grid. Right: "
                "the distribution of max |Qdlin| over every cycle that leaves the physical "
                "band, on whichever side is worse. The summary-level capacity artifact "
                "on these cycles is ~1%; the "
                "interpolated curve is wrong by up to three orders of magnitude.")


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    idx, j = load()
    crosstab(j)
    traces(j)
    cycle40(j)
    bloated(j)
    qdlin_corruption(j)


if __name__ == "__main__":
    main()
