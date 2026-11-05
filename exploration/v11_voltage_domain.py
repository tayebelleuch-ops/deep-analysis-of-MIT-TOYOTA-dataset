"""Stage 2, items 3 and 6: the voltage grid, dQ/dV peak alignment, and the paper's
early-prediction feature.

Reads the extracted HDF5 files rather than the raw .mat -- which also exercises the
extract as a consumer would use it.

Item 6 computes DeltaQ_100-10(V) and log10 of its variance. **No model is fitted and
nothing is tuned**: the only numbers reported are the feature and its correlation with
log cycle life, against the two values the paper itself reports.
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

OUT = HERE / "extract_out"
TABLES = HERE / "tables"
BATCHES = matr.BATCH_DATES

# The paper's feature uses cycles 10 and 100. Cycle numbering is NOT offset between
# batches (schema.md; confirmed independently by fig07), and 2017-05-12's missing cycle 1
# is retained as a placeholder rather than deleted, so cycle 10 and cycle 100 are the
# 10th and 100th recorded cycle in every batch and no per-batch offset is needed.
CYC_LO, CYC_HI = 10, 100
# The paper reports rho on a log-log axis, so both sides are log10.
PAPER_RHO_PANEL = -0.92     # Fig. 2c panel label
PAPER_RHO_CAPTION = -0.93   # Fig. 2c caption


def read_grid_rows(idx: pd.DataFrame, field: str,
                   want: pd.DataFrame) -> dict[tuple[str, int], np.ndarray]:
    """Pull specific (cell_uid, cycle) rows of one grid field out of the HDF5 files."""
    got = {}
    for date in BATCHES:
        sel = want[want.source_batch_date == date]
        if not len(sel):
            continue
        with h5py.File(OUT / f"within_cycle_{date}.h5", "r") as f:
            ds = f[f"grid/{field}"]
            order = sel.sort_values("h5_row")
            rows = order.h5_row.to_numpy()
            data = ds[np.sort(rows)]          # h5py needs an increasing selection
            for (uid, cyc), arr in zip(zip(order.cell_uid, order.cycle), data):
                got[(uid, int(cyc))] = arr.astype(np.float64)
    return got


def item3(idx: pd.DataFrame) -> None:
    print("\n" + "=" * 78 + "\nITEM 3  THE VOLTAGE GRID AND dQ/dV PEAK ALIGNMENT\n" + "=" * 78)
    grids = {}
    for date in BATCHES:
        with h5py.File(OUT / f"within_cycle_{date}.h5", "r") as f:
            grids[date] = f["vdlin"][:]
    ref = grids[BATCHES[0]]
    d = np.diff(ref)
    print(f"\n3a. the stored grid: {ref.size} points, {ref[0]} -> {ref[-1]} V, "
          f"step {d.min():.17g} .. {d.max():.17g}")
    print(f"    monotonically decreasing: {bool((d < 0).all())}")
    for date in BATCHES:
        print(f"    {date}: byte-identical to {BATCHES[0]}: "
              f"{bool(np.array_equal(grids[date], ref))}")
    ls = np.linspace(3.5, 2.0, 1000)
    print(f"    vs np.linspace(3.5, 2.0, 1000): n differing = {int((ref != ls).sum())}, "
          f"max |diff| = {np.abs(ref - ls).max():.3e}")
    print(f"    vs np.linspace(3.6, 2.0, 1000): max |diff| = "
          f"{np.abs(ref - np.linspace(3.6, 2.0, 1000)).max():.4f}  "
          f"(the brief's 3.6 V reading is refuted)")
    pd.DataFrame({"i": np.arange(1000), "vdlin_V": ref}).to_csv(
        TABLES / "v11_vdlin_grid.csv", index=False, float_format="%.17g")

    print("\n3b. dQ/dV peak voltage at cycle 100, by batch")
    print("    The peak is the grid voltage of min(discharge_dQdV) -- the field is <= 0,")
    print("    so its minimum is the strongest peak. Window: one cycle, cycle 100.")
    want = idx[(idx.cycle == 100) & idx.is_series_valid & ~idx.is_placeholder]
    dq = read_grid_rows(idx, "discharge_dQdV", want)
    rows = []
    for (uid, cyc), arr in dq.items():
        r = want[(want.cell_uid == uid) & (want.cycle == cyc)].iloc[0]
        k = int(np.argmin(arr))
        rows.append({"cell_uid": uid, "batch_date": r.source_batch_date,
                     "channel": int(r.source_channel), "peak_V": float(ref[k]),
                     "peak_dQdV": float(arr[k])})
    t = pd.DataFrame(rows)
    g = t.groupby("batch_date").peak_V.agg(["count", "median", "min", "max", "std"])
    print(g.to_string(float_format=lambda x: f"{x:.4f}"))
    t.to_csv(TABLES / "v11_dqdv_peak_cycle100.csv", index=False, float_format="%.6g")
    deg = t[t.peak_V < 2.001]
    print(f"    {len(deg)} of {len(t)} cells have their dQdV minimum at the LAST grid")
    print(f"    point (2.0 V) with magnitude {deg.peak_dQdV.min():.1f}..{deg.peak_dQdV.max():.1f}")
    print(f"    Ah/V -- an interpolation edge artifact, not a phase-transition peak:")
    for _, r in deg.iterrows():
        print(f"      {r.cell_uid} {r.batch_date} ch{int(r.channel)}")
    print("    excluding them, the peak is far tighter than the raw spread suggests:")
    g2 = t[t.peak_V > 2.001].groupby("batch_date").peak_V.agg(
        ["count", "median", "min", "max", "std"])
    print(g2.to_string(float_format=lambda x: f"{x:.4f}"))
    spread = g2["median"].max() - g2["median"].min()
    print(f"    spread of batch medians: {spread:.4f} V "
          f"({spread/abs(float(np.diff(ref)[0])):.1f} grid steps)")
    print("    -> REPORT.md section 4.4 uses this alignment (via fig07) as independent")
    print("       evidence that cycle indices are not offset between batches.")


def item6(idx: pd.DataFrame) -> None:
    print("\n" + "=" * 78 + "\nITEM 6  DeltaQ_100-10(V) AND ITS LOG VARIANCE\n" + "=" * 78)
    cells = pd.read_csv(HERE / "analysis_set_cells.csv")
    print(f"\ncycle indices used: {CYC_LO} and {CYC_HI}, in the analysis set's numbering.")
    print("Cycle numbering is not offset between batches and 2017-05-12's cycle 1 is a")
    print("retained placeholder, not a deletion, so no per-batch shift is applied.")

    want = idx[idx.cycle.isin([CYC_LO, CYC_HI])]
    have = want.groupby("cell_uid").cycle.nunique()
    both = set(have[have == 2].index)
    print(f"\ncells with both cycle {CYC_LO} and cycle {CYC_HI}: {len(both)} of {len(cells)}")
    missing = sorted(set(cells.cell_uid) - both)
    if missing:
        print(f"  cells missing one of them: {missing}")

    want = want[want.cell_uid.isin(both)]
    ql = read_grid_rows(idx, "Qdlin", want)
    with h5py.File(OUT / f"within_cycle_{BATCHES[0]}.h5", "r") as f:
        vdlin = f["vdlin"][:]

    rows = []
    for uid in sorted(both):
        a, b = ql[(uid, CYC_LO)], ql[(uid, CYC_HI)]
        dq = b - a
        c = cells[cells.cell_uid == uid].iloc[0]
        v10 = want[(want.cell_uid == uid) & (want.cycle == CYC_LO)].iloc[0]
        v100 = want[(want.cell_uid == uid) & (want.cycle == CYC_HI)].iloc[0]
        rows.append({
            "cell_uid": uid, "batch_date": c.batch_date, "channel": int(c.channel),
            "policy": c.policy_canonical,
            "cycle_life": c.eol_cycle_80pct_soh, "has_eol_label": bool(c.has_eol_label),
            "in_paper_124": bool(c.in_paper_124),
            "exclude_from_deltaq_features": bool(c.exclude_from_deltaq_features),
            "series_valid_c10": bool(v10.is_series_valid),
            "series_valid_c100": bool(v100.is_series_valid),
            "var_dq": float(np.var(dq)),
            "log10_var_dq": float(np.log10(np.var(dq))),
            "dq_min": float(dq.min()), "dq_max": float(dq.max()),
            "dq_mean": float(dq.mean()),
        })
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "v11_deltaq_feature.csv", index=False, float_format="%.8g")
    print(f"wrote tables/v11_deltaq_feature.csv ({len(t)} cells)")

    def rho(s: pd.DataFrame) -> tuple[float, int]:
        s = s[s.has_eol_label & np.isfinite(s.log10_var_dq)]
        if len(s) < 3:
            return np.nan, len(s)
        return float(np.corrcoef(s.log10_var_dq, np.log10(s.cycle_life))[0, 1]), len(s)

    base = t[~t.exclude_from_deltaq_features]
    excluded = t[t.exclude_from_deltaq_features]
    print(f"\nexcluded by exclude_from_deltaq_features: "
          f"{list(excluded.cell_uid)} "
          f"({', '.join(f'{r.batch_date} ch{r.channel}' for _, r in excluded.iterrows())})")

    shortest = base[base.has_eol_label].nsmallest(1, "cycle_life").iloc[0]
    print(f"shortest-lived cell among them: {shortest.cell_uid} "
          f"({shortest.batch_date} ch{int(shortest.channel)}), "
          f"cycle life {shortest.cycle_life:g}")

    print("\ncorrelation of log10(Var(DeltaQ_100-10(V))) with log10(cycle life):")
    variants = [
        ("all labelled cells with both cycles", t),
        ("minus exclude_from_deltaq_features", base),
        ("minus that cell AND the shortest-lived cell (the paper's Fig. 2c basis)",
         base[base.cell_uid != shortest.cell_uid]),
        ("in_paper_124 only", t[t.in_paper_124]),
        ("in_paper_124 minus the shortest-lived of them", None),
    ]
    p124 = t[t.in_paper_124]
    sp = p124[p124.has_eol_label].nsmallest(1, "cycle_life").iloc[0]
    variants[-1] = (f"in_paper_124 minus its shortest-lived ({sp.cell_uid})",
                    p124[p124.cell_uid != sp.cell_uid])
    out = []
    for label, s in variants:
        r, n = rho(s)
        out.append({"basis": label, "n_cells": n, "rho": r,
                    "vs_paper_panel_-0.92": r - PAPER_RHO_PANEL if np.isfinite(r) else np.nan,
                    "vs_paper_caption_-0.93": r - PAPER_RHO_CAPTION if np.isfinite(r) else np.nan})
        print(f"  {label:62s} n={n:3d}  rho={r:+.4f}")
    print(f"\n  the paper reports rho = {PAPER_RHO_PANEL} in its Fig. 2c panel label and")
    print(f"  {PAPER_RHO_CAPTION} in the same figure's caption, on 124 cells, log-log, with")
    print("  'the shortest lived battery' excluded from panels b and c. The two values")
    print("  disagree with each other by 0.01; the paper does not say which is which.")

    print("\nper batch (minus exclude_from_deltaq_features):")
    for b in BATCHES:
        r, n = rho(base[base.batch_date == b])
        out.append({"basis": f"batch {b}", "n_cells": n, "rho": r,
                    "vs_paper_panel_-0.92": r - PAPER_RHO_PANEL,
                    "vs_paper_caption_-0.93": r - PAPER_RHO_CAPTION})
        print(f"  {b}  n={n:3d}  rho={r:+.4f}")
    pd.DataFrame(out).to_csv(TABLES / "v11_deltaq_correlation.csv", index=False,
                             float_format="%.6g")

    bad = t[~t.series_valid_c10 | ~t.series_valid_c100]
    print(f"\ncells whose cycle {CYC_LO} or {CYC_HI} series fails a validity check: "
          f"{len(bad)}")
    if len(bad):
        print(bad[["cell_uid", "batch_date", "channel", "series_valid_c10",
                   "series_valid_c100", "log10_var_dq"]].to_string(index=False))


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    idx = pd.read_csv(OUT / "within_cycle_index.csv")
    item3(idx)
    item6(idx)


if __name__ == "__main__":
    main()
