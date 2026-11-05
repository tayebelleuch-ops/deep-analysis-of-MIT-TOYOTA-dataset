"""Stage 2, items 1, 2, 5 and 7: structure, consistency with the summary, the charge
profile, and rests / C-10 cycles.

Everything here reads `extract_out/within_cycle_index.csv`, whose diagnostic columns were
computed from the **float64** source during extraction, so no number below depends on the
float32 narrowing of the published arrays.

Each detector states its threshold and its window. Every window here is **one cycle**:
these are properties of a single series, which is what makes them independent of the
v1.0 summary-level detectors (`is_artifact_cycle` is an 11-cycle rolling median).

Writes tables to `tables/v11_*.csv` and prints the numbers quoted in `REPORT_v1.1.md`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "extract_out"
TABLES = HERE / "tables"
BATCHES = ["2017-05-12", "2017-06-30", "2018-04-12"]

# --- thresholds, stated ---------------------------------------------------------
NOMINAL_SAMPLING_S = 5.0        # the interval REPORT.md section 2 states for all batches
SAMPLING_TOL_S = 0.5            # a cycle is "at the nominal rate" within +-0.5 s
CAP = 1000                      # the external repo's pad/truncate length (4.7)
N_AGE_BINS = 4                  # quartiles of each cell's own life
CE_IMPOSSIBLE = 1.01            # REPORT.md section 4.4's physical ceiling on QD/QC


def load() -> pd.DataFrame:
    idx = pd.read_csv(OUT / "within_cycle_index.csv")
    # age = position within the cell's own record, 0..1, on the analysis set's numbering
    last = idx.groupby("cell_uid").cycle.transform("max")
    idx["age_frac"] = (idx.cycle - 1) / np.maximum(last - 1, 1)
    idx["age_bin"] = np.clip((idx.age_frac * N_AGE_BINS).astype(int), 0, N_AGE_BINS - 1)
    idx["measured"] = ~idx.is_placeholder
    return idx


def h(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


# ---------------------------------------------------------------------------
# item 1: structure
# ---------------------------------------------------------------------------

def item1(idx: pd.DataFrame) -> None:
    h("ITEM 1  STRUCTURE")
    m = idx[idx.measured]

    print("\n1a. samples per cycle, by batch and by quartile of life "
          "(measured cycles only; the 46 placeholders excluded)")
    t = m.pivot_table(index="source_batch_date", columns="age_bin",
                      values="n_samples", aggfunc="median")
    t.columns = [f"Q{c+1}_median" for c in t.columns]
    t["overall_median"] = m.groupby("source_batch_date").n_samples.median()
    t["min"] = m.groupby("source_batch_date").n_samples.min()
    t["max"] = m.groupby("source_batch_date").n_samples.max()
    t["n_cycles"] = m.groupby("source_batch_date").size()
    print(t.to_string())
    t.to_csv(TABLES / "v11_samples_per_cycle.csv")

    print("\n1b. sampling interval: median dt within each cycle (seconds)")
    rows = []
    for b in BATCHES:
        v = m.loc[m.source_batch_date == b, "dt_median_s"]
        near = v.sub(NOMINAL_SAMPLING_S).abs().le(SAMPLING_TOL_S)
        rows.append({"batch_date": b, "n_cycles": len(v),
                     "dt_median_s_p01": v.quantile(0.01), "dt_median_s_median": v.median(),
                     "dt_median_s_p99": v.quantile(0.99),
                     "dt_median_s_min": v.min(), "dt_median_s_max": v.max(),
                     f"n_within_{SAMPLING_TOL_S}s_of_{NOMINAL_SAMPLING_S}s": int(near.sum()),
                     "pct_at_nominal": 100 * near.mean()})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    t.to_csv(TABLES / "v11_sampling_interval.csv", index=False)
    print(f"  -> REPORT.md section 2 states ~{NOMINAL_SAMPLING_S:.0f} s for all three "
          f"batches. Cycles at that rate: {100*m.dt_median_s.sub(NOMINAL_SAMPLING_S).abs().le(SAMPLING_TOL_S).mean():.1f}% overall.")

    print("\n1c. non-monotonic and duplicated time")
    rows = []
    for b in BATCHES:
        s = m[m.source_batch_date == b]
        rows.append({
            "batch_date": b, "n_cycles": len(s),
            "n_cycles_with_dt<=0": int((s.n_dt_nonpositive > 0).sum()),
            "n_cycles_with_dt==0": int((s.n_dt_zero > 0).sum()),
            "n_cycles_with_dt<0": int(((s.n_dt_nonpositive - s.n_dt_zero) > 0).sum()),
            "cells_affected": int(s.loc[s.n_dt_nonpositive > 0, "cell_uid"].nunique()),
            "worst_n_dup_in_one_cycle": int(s.n_dt_zero.max()),
        })
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    t.to_csv(TABLES / "v11_time_monotonicity.csv", index=False)
    aff = m[m.n_dt_nonpositive > 0]
    if len(aff):
        print("  cells with any non-monotonic time:")
        g = aff.groupby(["source_batch_date", "source_channel", "cell_uid"]).agg(
            n_cycles=("cycle", "size"), worst_n_dup=("n_dt_zero", "max"),
            cycles=("cycle", lambda c: ",".join(map(str, sorted(c)[:8]))))
        print(g.to_string())
        g.to_csv(TABLES / "v11_time_monotonicity_cells.csv")

    print("\n1d. does t reset to zero at the start of every cycle?")
    print(f"  cycles with t[0] != 0      : {int((m.t_start_min != 0).sum())}")
    print(f"  max |t[0]| over all cycles : {m.t_start_min.abs().max():.6g} min")
    print("  (t is per-cycle elapsed time, so t[0] == 0 is expected; a non-zero start "
          "would mean the field carries test time instead)")

    print("\n1e. missing values per field")
    print(f"  cycles with any NaN in the six native series : {int((m.n_nan_native > 0).sum())}")
    print(f"  cycles with any NaN in the three grid series : {int((m.n_nan_grid > 0).sum())}")
    print(f"  total NaN values, native                    : {int(m.n_nan_native.sum())}")
    print(f"  total NaN values, grid                      : {int(m.n_nan_grid.sum())}")
    print("  -> extends REPORT.md section 4.4 ('no missing values anywhere'), which was "
          "established on the summary fields only, to the within-cycle series.")

    print(f"\n1f. truncation at a {CAP}-sample cap "
          f"(reproduces comparison_external_repos.md section 4.7)")
    rows = []
    for b in BATCHES:
        for ab in range(N_AGE_BINS):
            s = m[(m.source_batch_date == b) & (m.age_bin == ab)]
            over = s.n_samples > CAP
            lost = np.where(over, (s.n_samples - CAP) / s.n_samples, 0.0)
            rows.append({"batch_date": b, "age_quartile": f"Q{ab+1}", "n_cycles": len(s),
                         "pct_cycles_truncated": 100 * over.mean(),
                         "mean_pct_points_lost": 100 * lost.mean()})
        s = m[m.source_batch_date == b]
        over = s.n_samples > CAP
        lost = np.where(over, (s.n_samples - CAP) / s.n_samples, 0.0)
        rows.append({"batch_date": b, "age_quartile": "ALL", "n_cycles": len(s),
                     "pct_cycles_truncated": 100 * over.mean(),
                     "mean_pct_points_lost": 100 * lost.mean()})
    over = m.n_samples > CAP
    lost = np.where(over, (m.n_samples - CAP) / m.n_samples, 0.0)
    rows.append({"batch_date": "ALL", "age_quartile": "ALL", "n_cycles": len(m),
                 "pct_cycles_truncated": 100 * over.mean(),
                 "mean_pct_points_lost": 100 * lost.mean()})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    t.to_csv(TABLES / "v11_cap1000_truncation.csv", index=False)
    print("  -> that section probed 420 cycles and reported 59% of cycles losing data, "
          "averaging 9.4%.")


# ---------------------------------------------------------------------------
# item 2: consistency with the summary
# ---------------------------------------------------------------------------

def item2(idx: pd.DataFrame) -> None:
    h("ITEM 2  CONSISTENCY WITH THE SUMMARY")
    m = idx[idx.measured & idx.is_series_valid].copy()
    print(f"restricted to measured cycles whose series passes every check: {len(m):,} "
          f"of {int(idx.measured.sum()):,}")
    print("(the invalid ones are reported in item 4; including them would let a handful "
          "of corrupt rows dominate every residual below)")

    m["res_dis"] = m.Q_dis_integral_Ah - m.QDischarge_Ah
    m["res_chg"] = m.Q_chg_integral_Ah - m.QCharge_Ah
    m["res_qdlin"] = m.Qdlin_last - m.QDischarge_Ah
    m["rel_dqdv"] = m.dqdv_resid_rms / m.dqdv_num_absmax.replace(0, np.nan)

    specs = [
        ("integral(-I dt) - QDischarge", "res_dis", "Ah"),
        ("integral(+I dt) - QCharge", "res_chg", "Ah"),
        ("Qdlin[-1] (at 2.0 V) - QDischarge", "res_qdlin", "Ah"),
        ("Tdlin_max - T_max", "Tdlin_excess_over_T_max", "degC"),
        ("T_min - Tdlin_min", "Tdlin_shortfall_under_T_min", "degC"),
        ("RMS(d(Qdlin)/dVdlin - discharge_dQdV)", "dqdv_resid_rms", "Ah/V"),
        ("  the same, relative to |d(Qdlin)/dV|max", "rel_dqdv", "-"),
    ]
    rows = []
    for label, col, unit in specs:
        v = m[col].replace([np.inf, -np.inf], np.nan).dropna()
        rows.append({"quantity": label, "unit": unit, "n": len(v),
                     "median": v.median(), "p01": v.quantile(0.01),
                     "p99": v.quantile(0.99), "min": v.min(), "max": v.max(),
                     "median_abs": v.abs().median(), "p99_abs": v.abs().quantile(0.99)})
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + t.to_string(index=False, float_format=lambda x: f"{x:.6g}"))
    t.to_csv(TABLES / "v11_summary_consistency.csv", index=False)

    print("\nper batch, median residual:")
    g = m.groupby("source_batch_date")[["res_dis", "res_chg", "res_qdlin",
                                        "dqdv_resid_rms", "rel_dqdv"]].median()
    print(g.to_string(float_format=lambda x: f"{x:.6g}"))
    g.to_csv(TABLES / "v11_summary_consistency_by_batch.csv")

    print("\ncoulombic efficiency from the series, against REPORT.md section 4.4")
    ce_sum = m.QDischarge_Ah / m.QCharge_Ah
    ce_int = m.Q_dis_integral_Ah / m.Q_chg_integral_Ah
    print(f"  from the summary fields : median {ce_sum.median():.6f}, "
          f"n > {CE_IMPOSSIBLE} = {int((ce_sum > CE_IMPOSSIBLE).sum())}")
    print(f"  from the integrated series: median {ce_int.median():.6f}, "
          f"n > {CE_IMPOSSIBLE} = {int((ce_int > CE_IMPOSSIBLE).sum())}")
    print(f"  median excess QD - QC (summary): {(m.QDischarge_Ah - m.QCharge_Ah).median()*1000:.4f} mAh")


# ---------------------------------------------------------------------------
# item 5: charge profile
# ---------------------------------------------------------------------------

def item5(idx: pd.DataFrame) -> None:
    h("ITEM 5  CHARGE PROFILE: THE CV TAIL")
    print("CV share = charge-weighted time with V within 5 mV of the fixed 3.6 V cutoff,")
    print("divided by total time with I > 0.01 C. Window: one cycle. The cutoff is FIXED,")
    print("not keyed to each cycle's own maximum voltage -- cleaning_plan.md records that")
    print("keying it per cycle returned a spurious zero on 13 cells.")
    m = idx[idx.measured & idx.is_series_valid].copy()

    print("\n5a. CV share at cycle 10 and at each cell's last cycle, by batch")
    rows = []
    for b in BATCHES:
        s = m[m.source_batch_date == b]
        c10 = s[s.cycle == 10].cv_fraction
        lastc = s.groupby("cell_uid").cycle.transform("max")
        cl = s[s.cycle == lastc].cv_fraction
        rows.append({"batch_date": b, "n_cells_cycle10": len(c10),
                     "cv_cycle10_median": c10.median(), "cv_cycle10_min": c10.min(),
                     "cv_cycle10_max": c10.max(), "n_cells_last": len(cl),
                     "cv_last_median": cl.median(), "cv_last_min": cl.min(),
                     "cv_last_max": cl.max()})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    t.to_csv(TABLES / "v11_cv_fraction_by_batch.csv", index=False)
    print("  -> REPORT.md section 8 reports 0.315-0.330 at cycle 10 and "
          "0.842 / 0.863 / 0.654 at the last cycle.")

    print("\n5b. CV share by quartile of life")
    t = m.pivot_table(index="source_batch_date", columns="age_bin",
                      values="cv_fraction", aggfunc="median")
    t.columns = [f"Q{c+1}" for c in t.columns]
    print(t.to_string(float_format=lambda x: f"{x:.4f}"))
    t.to_csv(TABLES / "v11_cv_fraction_by_age.csv")

    print("\n5c. CV share by policy (median over each policy's cells, at cycle 10 and last)")
    cells = pd.read_csv(HERE / "analysis_set_cells.csv")
    pol = dict(zip(cells.cell_uid, cells.policy_canonical))
    m["policy"] = m.cell_uid.map(pol)
    lastc = m.groupby("cell_uid").cycle.transform("max")
    agg = []
    for (b, p), s in m.groupby(["source_batch_date", "policy"]):
        agg.append({"batch_date": b, "policy": p, "n_cells": s.cell_uid.nunique(),
                    "cv_cycle10_median": s[s.cycle == 10].cv_fraction.median(),
                    "cv_last_median": s[s.cycle == lastc.loc[s.index]].cv_fraction.median(),
                    "cv_all_median": s.cv_fraction.median()})
    t = pd.DataFrame(agg).sort_values(["batch_date", "policy"])
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    t.to_csv(TABLES / "v11_cv_fraction_by_policy.csv", index=False)


# ---------------------------------------------------------------------------
# item 7: rests and C/10 cycles
# ---------------------------------------------------------------------------

def item7(idx: pd.DataFrame) -> None:
    h("ITEM 7  RESTS AND C/10 CYCLES")
    m = idx[idx.measured]
    print("A C/10 cycle would charge and discharge at ~0.1 C, so its peak |I| would be")
    print("~0.1. Threshold: a cycle counts as low-rate if peak |I| < 1.0 C, which is 10x")
    print("above C/10 and 4x below the lowest programmed rate (4C discharge).")
    rows = []
    for b in BATCHES:
        s = m[m.source_batch_date == b]
        rows.append({"batch_date": b, "n_cycles": len(s),
                     "I_peak_abs_min": s.I_peak_abs.min(),
                     "I_peak_abs_p01": s.I_peak_abs.quantile(0.01),
                     "I_peak_abs_median": s.I_peak_abs.median(),
                     "I_peak_abs_max": s.I_peak_abs.max(),
                     "n_cycles_peak_below_1C": int((s.I_peak_abs < 1.0).sum()),
                     "n_cycles_peak_below_0.5C": int((s.I_peak_abs < 0.5).sum())})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    t.to_csv(TABLES / "v11_low_rate_cycles.csv", index=False)
    low = m[m.I_peak_abs < 1.0]
    print(f"\n  cycles anywhere with peak |I| < 1.0 C: {len(low)}")
    if len(low):
        print(low[["cell_uid", "cycle", "source_batch_date", "source_channel",
                   "I_peak_abs", "n_samples", "t_end_min"]].head(20).to_string(index=False))
    print("  -> REPORT.md section 4.2 item 3 scanned the first and last three cycles of all")
    print("     140 rows (840 cycles) and found a 4.00 C floor. This scans all 114,692")
    print("     measured cycles.")

    print("\n7b. rest segments: longest contiguous |I| < 0.01 C run per cycle, by batch")
    rows = []
    for b in BATCHES:
        s = m[m.source_batch_date == b]
        rows.append({"batch_date": b,
                     "rest_longest_s_median": s.rest_longest_s.median(),
                     "rest_longest_s_p95": s.rest_longest_s.quantile(0.95),
                     "rest_longest_s_max": s.rest_longest_s.max(),
                     "n_rest_runs_median": s.n_rest_runs.median(),
                     "n_rest_samples_median": s.n_rest_samples.median()})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    t.to_csv(TABLES / "v11_rest_segments.csv", index=False)
    print("  -> REPORT.md section 4.1 measured, from a sample: one run of 55.8-60.9 s /")
    print("     two of 295.8 + 295.0 s / 10.1 + 4 + 4 s for the three batches.")


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    idx = load()
    print(f"index: {len(idx):,} rows; measured {int(idx.measured.sum()):,}; "
          f"series-valid {int(idx.is_series_valid.sum()):,}")
    item1(idx)
    item2(idx)
    item5(idx)
    item7(idx)


if __name__ == "__main__":
    main()
