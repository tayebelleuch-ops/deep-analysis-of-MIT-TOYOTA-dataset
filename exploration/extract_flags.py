"""Stage 1b: turn the recorded per-cycle diagnostics into series-level validity flags.

Reads `extract_out/within_cycle_index_raw.csv`, applies the thresholds below and writes
`extract_out/within_cycle_index.csv` -- the published index -- plus two evidence tables.

**Every threshold is a named constant here and nowhere else**, so that no flag in the
published files rests on a number that is not written down, which is the rule
`REPORT.md` section 4.3.1 sets for the v1.0 detectors. Each flag answers one question
about the series; `is_series_valid` is their conjunction, exactly as `is_clean_cycle` is
the conjunction of the four v1.0 summary-level flags.

These flags are **independent of** and **additional to** the v1.0 flags. Nothing in
`analysis_set_cycles.csv` is modified. Where a cycle is `is_clean_cycle = True` in v1.0
but fails a series check here, the row is written to
`tables/v11_proposed_clean_cycle_corrections.csv` as a *proposal* for the maintainer to
decide on -- not applied.

Window note: every check below is **within a single cycle**. None uses a rolling window
over neighbouring cycles, which is what makes them independent of the v1.0 detectors
(`is_artifact_cycle` is an 11-cycle rolling median on `QDischarge`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "extract_out"
TABLES = HERE / "tables"

# --- thresholds, with the reasoning for each ---------------------------------------
# Every cutoff below was placed in an OBSERVED GAP in the measured distribution, not
# chosen a priori. The gap each one sits in is quoted. Where no gap separates signal
# from background, the quantity is reported as a graded observation in REPORT_v1.1.md
# and is NOT used as a flag -- the rule REPORT.md section 4.3.1 sets for U2 and U12.
#
# A real cycle is ~700-1400 samples. 10 is far below any measurement and above the
# 2-sample placeholders, so this separates "there is a series" from "there is not".
MIN_SAMPLES = 10
# Sampling is ~5 s and the largest ordinary step observed anywhere is 5.1 s. A
# 10-minute step inside one cycle cannot be sampling; it means the row splices together
# fragments recorded at different times. Observed gap: ordinary steps top out at 5.1 s,
# the next largest is >1 h.
MAX_GAP_S = 600.0
# A normal cycle runs 38-60 min. Observed gap: ordinary cycles end below 65 min, the
# next longest ends above 200 min.
MAX_DURATION_MIN = 240.0
# Cycle-length bloat. 5x the cell's own batch median; the length distribution is tight
# (batch p25-p75 within +-5% of the median), so 5x is far outside it.
LEN_MULT = 5.0
# Cutoffs are 2.0 V and 3.6 V on all three batches. Observed gaps: the highest V_max is
# 3.669 V and the next is 4.462 V, so 3.70 separates a plausible IR overshoot (<2% over
# the cutoff) from a physically impossible reading; the lowest ordinary V_min is 1.889 V
# and the next lower is 1.743 V, so 1.80 does the same below. 4.46-6.61 V is not
# achievable by an LFP/graphite cell.
V_LO, V_HI = 1.80, 3.70
# Peak current is judged against THE CELL'S OWN maximum programmed rate, not an absolute
# ceiling: 2017-05-12 contains 7C and 8C charging policies, so an absolute cutoff of 7 C
# would flag 8,600 cycles that are simply doing what they were programmed to do.
# Observed: the ratio has a tight systematic band (median 1.0004, with 490 cycles between
# 1.09 and 1.12 -- current overshoot at step transitions), then an empty stretch from
# 1.272 to 2.062. 1.50 sits in that gap and flags only the three cycles that draw ~12 C
# against a programmed 5-5.9 C. The 1.10-1.30 band is reported, not flagged, because no
# cutoff separates it from the background.
I_RATIO_MAX = 1.50
I_RATIO_DISCHARGE_FLOOR = 4.0    # every policy discharges at 4C, so the rate is >= 4
# Physically possible range for a 1.1 Ah cell's interpolated discharge curve, with
# generous headroom: no cell ever measured above 1.0787 Ah.
QDLIN_LO, QDLIN_HI = -0.10, 1.50
# Chamber is 30 C; the hottest sample anywhere is 44.7 C. 0-80 C is deliberately wide.
TDLIN_LO, TDLIN_HI = 0.0, 80.0
# dQdV is <= 0 by construction. The widest legitimate magnitude observed is 32 Ah/V.
DQDV_LO, DQDV_HI = -200.0, 1e-9
# Tolerance for "time increases". The most negative step anywhere is -2.9e-11 s, i.e.
# float64 rounding in MATLAB's own time arithmetic on 258 cycles across 86 cells, not a
# reversal. -60 microseconds is nine orders of magnitude above that rounding and four
# below the 5 s sampling interval, so it separates representation noise from a real
# reversal. Exactly-zero steps (duplicated timestamps, 35 cycles) are counted in
# `n_dt_zero` and reported, but are not treated as invalidating: one repeated sample in
# ~1000 does not make a series unusable.
DT_TOL_MIN = -1e-6

FLAGS = [
    "series_present", "series_time_monotone", "series_time_contiguous",
    "series_duration_plausible", "series_length_plausible", "series_voltage_in_range",
    "series_current_in_range", "series_grid_in_range", "series_no_nan",
]


def add_flags(idx: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    idx = idx.copy()
    rates = cells.set_index("cell_uid")[["policy_C1", "policy_C2"]]
    idx = idx.join(rates, on="cell_uid")
    # per-batch median native length, computed over measured cycles only so the 46
    # placeholders cannot drag the median down
    meas = idx.n_samples >= MIN_SAMPLES
    med = idx[meas].groupby("source_batch_date").n_samples.median()
    idx["batch_median_n_samples"] = idx.source_batch_date.map(med)

    idx["series_present"] = idx.n_samples >= MIN_SAMPLES
    idx["series_time_monotone"] = idx.dt_min_s.ge(DT_TOL_MIN * 60.0)
    idx["series_time_contiguous"] = idx.dt_max_s.le(MAX_GAP_S)
    idx["series_duration_plausible"] = idx.t_end_min.le(MAX_DURATION_MIN)
    idx["series_length_plausible"] = idx.n_samples.le(LEN_MULT * idx.batch_median_n_samples)
    idx["series_voltage_in_range"] = idx.V_min.ge(V_LO) & idx.V_max.le(V_HI)
    prog = (idx[["policy_C1", "policy_C2"]].max(axis=1)
            .clip(lower=I_RATIO_DISCHARGE_FLOOR))
    idx["programmed_rate_C"] = prog
    idx["I_peak_over_programmed"] = idx.I_peak_abs / prog
    idx["series_current_in_range"] = idx.I_peak_over_programmed.le(I_RATIO_MAX)
    grid_ok = (idx.Qdlin_min.ge(QDLIN_LO) & idx.Qdlin_max.le(QDLIN_HI)
               & idx.Tdlin_min.ge(TDLIN_LO) & idx.Tdlin_max.le(TDLIN_HI)
               & idx.dQdV_min.ge(DQDV_LO) & idx.dQdV_max.le(DQDV_HI))
    # a placeholder has no grid to judge; it already fails series_present
    idx["series_grid_in_range"] = grid_ok | idx.grid_len_raw.ne(1000)
    idx["series_no_nan"] = idx.n_nan_native.eq(0) & idx.n_nan_grid.eq(0)

    # the placeholders fail several checks for the same reason -- that they are not
    # measurements. They are excluded from the value-range checks so that each flag
    # reports only what it is meant to.
    for f in ("series_time_monotone", "series_time_contiguous",
              "series_duration_plausible", "series_voltage_in_range",
              "series_current_in_range"):
        idx.loc[~idx.series_present, f] = True

    idx["is_series_valid"] = idx[FLAGS].all(axis=1)
    return idx


def main() -> None:
    idx = pd.read_csv(OUT / "within_cycle_index_raw.csv")
    cells = pd.read_csv(HERE / "analysis_set_cells.csv")
    idx = add_flags(idx, cells)
    cy = pd.read_csv(HERE / "analysis_set_cycles.csv")

    idx["in_analysis_set"] = idx.set_index(["cell_uid", "cycle"]).index.isin(
        cy.set_index(["cell_uid", "cycle"]).index)

    # --- published column order: keys, flags, summary fields, then diagnostics
    keys = ["cell_uid", "cycle", "segment", "source_batch_date", "source_channel",
            "source_struct_index", "source_cycle_index", "h5_row", "n_samples",
            "grid_len_raw"]
    status = ["in_analysis_set", "beyond_crossing", "is_placeholder",
              "is_series_valid"] + FLAGS
    summary = ["QDischarge_Ah", "QCharge_Ah", "IR_ohm", "Tavg_C", "Tmax_C", "Tmin_C",
               "chargetime_min"]
    rest = [c for c in idx.columns if c not in keys + status + summary]
    idx = idx[keys + status + summary + rest]
    idx.to_csv(OUT / "within_cycle_index.csv", index=False, float_format="%.10g")
    print(f"within_cycle_index.csv: {len(idx):,} rows x {len(idx.columns)} columns")

    # --- evidence table: how many cycles each check rejects
    rowsum = []
    for f in FLAGS + ["is_series_valid"]:
        bad = ~idx[f]
        rowsum.append({
            "check": f,
            "n_fail": int(bad.sum()),
            "n_cells": int(idx.loc[bad, "cell_uid"].nunique()),
            "n_fail_2017-05-12": int((bad & idx.source_batch_date.eq("2017-05-12")).sum()),
            "n_fail_2017-06-30": int((bad & idx.source_batch_date.eq("2017-06-30")).sum()),
            "n_fail_2018-04-12": int((bad & idx.source_batch_date.eq("2018-04-12")).sum()),
        })
    TABLES.mkdir(exist_ok=True)
    pd.DataFrame(rowsum).to_csv(TABLES / "v11_series_validity_summary.csv", index=False)
    print(pd.DataFrame(rowsum).to_string(index=False))

    band = idx[(idx.I_peak_over_programmed > 1.10)
               & (idx.I_peak_over_programmed <= I_RATIO_MAX)]
    print(f"\nreported but NOT flagged: {len(band)} cycles draw 1.10-{I_RATIO_MAX:.2f}x "
          f"their cell's programmed rate, across {band.cell_uid.nunique()} cells. No "
          f"cutoff separates them from the systematic overshoot band, so they are "
          f"recorded as a graded observation rather than a flag.")
    dup = idx[(idx.n_dt_zero > 0) & ~idx.is_placeholder]
    print(f"also reported, not flagged: {len(dup)} measured cycles contain a duplicated "
          f"timestamp (one zero-length step), across {dup.cell_uid.nunique()} cells. The "
          f"46 placeholders also have a zero step and are excluded from that count.")

    # --- proposed v1.0 corrections: clean in v1.0, invalid on its own series
    j = idx.merge(cy[["cell_uid", "cycle", "is_clean_cycle", "is_artifact_cycle",
                      "is_restart_cycle", "is_junction_cycle", "is_measured_cycle"]],
                  on=["cell_uid", "cycle"], how="inner")
    contra = j[j.is_clean_cycle & ~j.is_series_valid].copy()
    contra["failed_checks"] = [
        ";".join(f for f in FLAGS if not r[f]) for _, r in contra.iterrows()]
    cols = ["cell_uid", "cycle", "source_batch_date", "source_channel",
            "failed_checks", "n_samples", "batch_median_n_samples", "t_end_min",
            "dt_max_s", "n_dt_zero", "V_min", "V_max", "I_peak_abs",
            "I_peak_over_programmed",
            "Qdlin_min", "Qdlin_max", "QDischarge_Ah"]
    contra[cols].sort_values(["source_batch_date", "source_channel", "cycle"]).to_csv(
        TABLES / "v11_proposed_clean_cycle_corrections.csv", index=False,
        float_format="%.6g")
    print(f"\nPROPOSED v1.0 corrections (is_clean_cycle=True but series invalid): "
          f"{len(contra)} cycles across {contra.cell_uid.nunique()} cells")
    print("  -> tables/v11_proposed_clean_cycle_corrections.csv (proposal only; "
          "analysis_set_cycles.csv is NOT modified)")
    if len(contra):
        print(contra[["cell_uid", "cycle", "source_batch_date", "source_channel",
                      "failed_checks"]].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
