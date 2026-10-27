"""Step 2: test every claim on the four dataset pages against the files.

Each `check_*` function returns a tidy DataFrame and is written to
exploration/tables/<name>.csv. Nothing here modifies, drops or relabels data:
the checks measure, and where a measurement contradicts a page the row carries
both the page's claim and the measured value so the disagreement stays visible.

Two structural limits of the data constrain what is testable at all:

* `cycles[*]["t"]` restarts at 0 every cycle, and the struct carries no absolute
  timestamp, test-time or date field. So a "computer restart left time gaps" claim
  cannot be checked directly -- only through its effects (a capacity spike from the
  implied rest, or an abnormal cycle duration).
* The IR pulse (30 vs 33 ms) happens inside a cycle at 80% SOC, but the within-cycle
  sampling interval is ~2-3 s. A 3 ms difference is ~1000x below the sampling
  resolution, so the pulse width is not measurable from these files at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr
import transcript_issues as ti
from inventory import first_valid_index

TABLES = HERE / "tables"
REST_I = 0.01       # |I| (C-rate) below which a sample counts as rest / open circuit
EARLY = slice(0, 100)   # "early life" window, applied after the leading placeholder


def _meta():
    if not hasattr(_meta, "cache"):
        _meta.cache = {d: matr.read_batch_metadata(d) for d in matr.BATCH_DATES}
    return _meta.cache


def _valid_summary(r):
    """A cell's summary with the leading placeholder cycle removed (2017-05-12)."""
    k = first_valid_index(r.summary["QDischarge"])
    return {f: v[k:] for f, v in r.summary.items()}, k


def _runs(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            out.append((i, j - 1)); i = j
        else:
            i += 1
    return out


# ==========================================================================
# A. summary-level checks
# ==========================================================================

def check_cycle_indexing() -> pd.DataFrame:
    """2017-05-12 page: 'Cycle 1 data is not available in the struct.'
    Does that shift cycle indices relative to the other two batches?"""
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            cyc = r.summary["cycle"]
            qd = r.summary["QDischarge"]
            k = first_valid_index(qd)
            rows.append({
                "batch_date": d, "channel": r.channel,
                "cycle_first": float(cyc[0]), "cycle_last": float(cyc[-1]),
                "n_summary_cycles": len(cyc), "n_cycles_group": r.n_cycles,
                "summary_len_eq_cycles_len": len(cyc) == r.n_cycles,
                "cycle_numbering_contiguous": bool(np.all(np.diff(cyc) == 1)),
                "n_leading_placeholder": k,
                "QD_at_index0_Ah": float(qd[0]),
            })
    return pd.DataFrame(rows)


def check_capacity_spikes(window: int = 11, abs_thresh: float = 0.01) -> pd.DataFrame:
    """2017-06-30 page: a restart 'around cycle 250 for most policies' left
    capacity 'spikes'. One row per detected spike, so the cycle at which they
    cluster is visible per batch.

    Deviation is measured against a centred rolling median, which tracks the fade
    trend, so a flagged point is a departure from the cell's own local level rather
    than from any global threshold. 0.01 Ah is ~10x the normal cycle-to-cycle step
    (~1e-3 Ah) and well below the known artifacts (~0.5-1.8 Ah).
    """
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, k = _valid_summary(r)
            qd = pd.Series(s["QDischarge"])
            med = qd.rolling(window, center=True, min_periods=1).median()
            dev = qd - med
            for i in np.flatnonzero(np.abs(dev.to_numpy()) > abs_thresh):
                rows.append({
                    "batch_date": d, "channel": r.channel,
                    "cycle": float(s["cycle"][i]),
                    "QD_Ah": float(qd.iloc[i]),
                    "local_median_Ah": float(med.iloc[i]),
                    "deviation_Ah": float(dev.iloc[i]),
                    "direction": "up" if dev.iloc[i] > 0 else "down",
                })
    return pd.DataFrame(rows)


def check_chargetime() -> pd.DataFrame:
    """Charge time 0-80% SOC: page says ~8-13.3 min (2017-05-12) and fixed at
    10 min (other two). `summary["chargetime"]` is in minutes."""
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            ct = s["chargetime"]
            early = ct[EARLY]
            rows.append({
                "batch_date": d, "channel": r.channel,
                "policy_canonical": matr.parse_policy(r.policy_readable)["canonical"],
                "chargetime_median_early_min": float(np.nanmedian(early)),
                "chargetime_min_min": float(np.nanmin(ct)),
                "chargetime_max_min": float(np.nanmax(ct)),
                "chargetime_p99_min": float(np.nanpercentile(ct, 99)),
                "n_nan": int(np.sum(~np.isfinite(ct))),
                "page_claim": ti.DESIGN[d]["charge_time_min_0_80_soc"],
            })
    return pd.DataFrame(rows)


def check_ir() -> pd.DataFrame:
    """Internal resistance: missing or implausible values per cell."""
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            ir = s["IR"]
            finite = ir[np.isfinite(ir)]
            rows.append({
                "batch_date": d, "channel": r.channel,
                "n_cycles": len(ir),
                "n_nan": int(np.sum(~np.isfinite(ir))),
                "n_nonpositive": int(np.sum(finite <= 0)),
                "n_zero_exact": int(np.sum(finite == 0)),
                "IR_median_ohm": float(np.nanmedian(ir)),
                "IR_min_ohm": float(np.nanmin(finite)) if finite.size else np.nan,
                "IR_max_ohm": float(np.nanmax(finite)) if finite.size else np.nan,
                "IR_early_median_ohm": float(np.nanmedian(ir[EARLY])),
            })
    return pd.DataFrame(rows)


def check_temperature() -> pd.DataFrame:
    """Thermocouple claims: 2017-05-12 ch 15/16 switched; 2017-06-30 ch 7 and 21
    fell off and ch 15/16 switched. Also the baseline-chamber-temperature spread
    that 2017-05-12 warns about.

    `T_rise` (median Tmax - Tmin over early cycles) is the discriminating quantity:
    a thermocouple in good contact tracks the cell and swings with the charge
    current, one that has fallen off tracks chamber air and barely swings. A pair
    swapped WITH EACH OTHER both stay in contact, so a swap shows up not as a small
    rise but as each cell reporting the rise its partner's policy predicts.
    """
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            tmax, tmin, tavg = s["Tmax"], s["Tmin"], s["Tavg"]
            pol = matr.parse_policy(r.policy_readable)
            rows.append({
                "batch_date": d, "channel": r.channel,
                "policy_canonical": pol["canonical"],
                "policy_C1": pol["C1"], "policy_C2": pol["C2"],
                "Tavg_early_C": float(np.nanmedian(tavg[EARLY])),
                "Tmin_early_C": float(np.nanmedian(tmin[EARLY])),
                "Tmax_early_C": float(np.nanmedian(tmax[EARLY])),
                "T_rise_early_C": float(np.nanmedian((tmax - tmin)[EARLY])),
                "Tavg_whole_C": float(np.nanmedian(tavg)),
                "T_rise_whole_C": float(np.nanmedian(tmax - tmin)),
                "n_Tmax_lt_Tmin": int(np.sum(tmax < tmin)),
                "n_nan_Tavg": int(np.sum(~np.isfinite(tavg))),
                "page_note": "; ".join(ti.cell_issues(d, r.channel)) or "",
            })
    return pd.DataFrame(rows)


def check_eol_criterion() -> pd.DataFrame:
    """The 75%-vs-0.88 Ah contradiction on the 2017-06-30 page: what capacity do
    the cells of each batch actually end at, in Ah and as a fraction of the
    1.1 Ah nominal?"""
    rows = []
    for d, recs in _meta().items():
        last = np.array([r.summary["QDischarge"][-1] for r in recs])
        # exclude the cells the pages say were stopped early, and the paused ones
        stop_early = {ch for (bd, ch), v in ti.CELL_ISSUES.items()
                      if bd == d and any("terminated before" in m or "resumed in" in m
                                         for m in v)}
        keep = np.array([r.channel not in stop_early for r in recs])
        sel = last[keep]
        rows.append({
            "batch_date": d,
            "n_cells_total": len(recs),
            "n_cells_ran_to_completion": int(keep.sum()),
            "QD_last_min_Ah": float(sel.min()), "QD_last_median_Ah": float(np.median(sel)),
            "QD_last_max_Ah": float(sel.max()),
            "pct_of_nominal_median": float(np.median(sel) / matr.NOMINAL_CAPACITY_AH * 100),
            "n_below_0.88Ah": int((sel < matr.EOL_THRESHOLD_AH).sum()),
            "n_below_0.825Ah": int((sel < matr.EOL_75PCT_AH).sum()),
            "page_claim": ti.DESIGN[d]["eol_criterion_as_printed"],
        })
    return pd.DataFrame(rows)


def check_missing_summary_data() -> pd.DataFrame:
    """Per-cell missing-value and physical-plausibility summary (plot 10's table)."""
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, k = _valid_summary(r)
            rec = {"batch_date": d, "channel": r.channel,
                   "n_cycles": len(s["cycle"]), "n_leading_placeholder": k}
            for f in ("QDischarge", "QCharge", "IR", "Tavg", "Tmin", "Tmax", "chargetime"):
                v = s[f]
                rec[f"n_nan_{f}"] = int(np.sum(~np.isfinite(v)))
                rec[f"n_nonpos_{f}"] = int(np.sum(v[np.isfinite(v)] <= 0))
            rec["n_Tmax_lt_Tmin"] = int(np.sum(s["Tmax"] < s["Tmin"]))
            # Coulombic efficiency. A bare QD > QC test fires on ~2/3 of all cycles
            # because QD exceeds QC by a systematic ~0.2 mAh (CE ~ 1.0002), which is
            # integration resolution on a 1.07 Ah measurement, not a defect. Only
            # CE above 1.01 is physically impossible at this scale, and those cycles
            # turn out to be the restart artifacts.
            ce = s["QDischarge"] / s["QCharge"]
            rec["ce_median"] = float(np.nanmedian(ce))
            rec["ce_max"] = float(np.nanmax(ce))
            rec["n_ce_above_1.01"] = int(np.sum(ce > 1.01))
            rec["max_QD_minus_QC_Ah"] = float(np.nanmax(s["QDischarge"] - s["QCharge"]))
            rec["cycle_monotonic"] = bool(np.all(np.diff(s["cycle"]) == 1))
            rows.append(rec)
    return pd.DataFrame(rows)


def check_ir_zero_cycles() -> pd.DataFrame:
    """Every cycle recording IR = 0 exactly, with its cycle number.

    Worth its own table because these turn out not to be random: all 22 of them sit on
    a computer restart, which makes IR = 0 a second, independent restart detector --
    and the three in 2017-06-30 identify an interruption that `check_time_gaps` misses
    because none of the affected cells happened to be mid-charge.
    """
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            for i in np.flatnonzero(s["IR"] <= 0):
                rows.append({"batch_date": d, "channel": r.channel,
                             "barcode": r.barcode, "cycle": float(s["cycle"][i]),
                             "QD_this_cycle_Ah": float(s["QDischarge"][i])})
    return pd.DataFrame(rows)


def check_continuation_junction() -> pd.DataFrame:
    """The capacity step where a paused cell's two segments meet.

    Compares the median of the 10 cycles each side, against the cell's own fade over
    10 cycles (from a linear fit to the 50 cycles before the pause) so the step can be
    told apart from continued ageing. The 2017-05-12 page predicts a rise.
    """
    import pandas as _pd
    inv = _pd.read_csv(HERE / "cell_inventory.csv")
    meta = {d: {r.channel: r for r in _meta()[d]} for d in matr.BATCH_DATES}
    rows = []
    for _, row in inv[inv.is_continuation].iterrows():
        segs = [x.split(":ch") for x in row.all_segments.split(" | ")]
        a = meta[segs[0][0]][int(segs[0][1])].summary["QDischarge"]
        b = meta[segs[1][0]][int(segs[1][1])].summary["QDischarge"]
        pre, post = float(np.median(a[-10:])), float(np.median(b[:10]))
        slope = float(np.polyfit(np.arange(50), a[-50:], 1)[0])
        rows.append({
            "barcode": row.barcode, "channel": int(row.channel),
            "policy_canonical": row.policy_canonical,
            "pre_median_Ah": pre, "post_median_Ah": post,
            "step_Ah": post - pre,
            "own_fade_per_10_cycles_Ah": slope * 10,
            "step_vs_own_fade": (post - pre) / (slope * 10) if slope else np.nan,
            "page_claim": "rise in capacity upon resuming",
        })
    return pd.DataFrame(rows)


# ==========================================================================
# B. derived / model-based checks appended after the first pass
# ==========================================================================

def heat_proxy(C1, Q1, C2) -> float:
    """Relative ohmic heat dissipated over the fast-charge portion of a cycle.

    For a two-step policy the cell spends Q1/C1 (in units of hours x 100) at C1
    and (80-Q1)/C2 at C2, and I^2.R heating integrates to
        C1^2 * (Q1/C1) + C2^2 * ((80-Q1)/C2) = C1*Q1 + C2*(80-Q1).
    The 1C CC-CV tail to 100% SOC and the 4C discharge are identical for every
    cell, so they shift the proxy by a constant and do not affect ranking. Used
    only to give the thermocouple checks an expected temperature rise per policy.
    """
    if not np.isfinite(C1) or not np.isfinite(Q1):
        return np.nan
    if not np.isfinite(C2):
        return C1 * 80.0
    return C1 * Q1 + C2 * (80.0 - Q1)


def check_thermocouple_outliers() -> pd.DataFrame:
    """Rank cells by how far their temperature rise sits below what their charging
    policy predicts, which is the signature of a thermocouple in poor contact.

    `T_rise_resid_C` is the residual of a per-batch least-squares fit of
    T_rise on `heat_proxy`. Also reports T_rise early vs late in life, because a
    thermocouple that falls off part-way through shows a step down rather than a
    low average -- 2017-06-30's page says ch 7 and 21 were found detached only on
    unloading, which would be a late-life effect.
    """
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            rise = (s["Tmax"] - s["Tmin"])
            n = len(rise)
            pol = matr.parse_policy(r.policy_readable)
            rows.append({
                "batch_date": d, "channel": r.channel, "barcode": r.barcode,
                "policy_canonical": pol["canonical"],
                "heat_proxy": heat_proxy(pol["C1"], pol["Q1"], pol["C2"]),
                "T_rise_early_C": float(np.nanmedian(rise[:100])),
                "T_rise_late_C": float(np.nanmedian(rise[-100:])),
                "T_rise_first_quarter_C": float(np.nanmedian(rise[: max(1, n // 4)])),
                "T_rise_last_quarter_C": float(np.nanmedian(rise[-max(1, n // 4):])),
                "Tmin_early_C": float(np.nanmedian(s["Tmin"][:100])),
                "page_note": "; ".join(ti.cell_issues(d, r.channel)) or "",
            })
    df = pd.DataFrame(rows)
    df["T_rise_late_minus_early_C"] = df["T_rise_late_C"] - df["T_rise_early_C"]
    df["T_rise_resid_C"] = np.nan
    for d, g in df.groupby("batch_date"):
        ok = g["heat_proxy"].notna() & g["T_rise_early_C"].notna()
        if ok.sum() > 3:
            x, y = g.loc[ok, "heat_proxy"].to_numpy(), g.loc[ok, "T_rise_early_C"].to_numpy()
            b, a = np.polyfit(x, y, 1)
            df.loc[g.index[ok], "T_rise_resid_C"] = y - (a + b * x)
    return df.sort_values(["batch_date", "T_rise_resid_C"])


def check_thermocouple_swap() -> pd.DataFrame:
    """Test the ch 15 / ch 16 swap claim where it is testable at all.

    A swap between two cells running the SAME policy is unobservable: their
    expected temperatures are identical, so no measurement can distinguish the
    swapped from the unswapped assignment. That is the situation in 2017-05-12,
    where ch 15 and ch 16 are each other's only replicate on 5.4C(60%)-3C. In
    2017-06-30 the two channels run different policies, so the assignment is
    testable: compare the squared residuals of (ch15, ch16) temperatures against
    their own policies with the residuals obtained after exchanging them.
    """
    out = []
    for d in matr.BATCH_DATES:
        g = check_thermocouple_outliers()
        g = g[g.batch_date == d]
        pair = g[g.channel.isin([15, 16])]
        if len(pair) != 2:
            continue
        a, b = pair.iloc[0], pair.iloc[1]
        same_policy = a.policy_canonical == b.policy_canonical
        ok = g["heat_proxy"].notna() & g["T_rise_early_C"].notna()
        slope, inter = np.polyfit(g.loc[ok, "heat_proxy"], g.loc[ok, "T_rise_early_C"], 1)
        pred = lambda hp: inter + slope * hp
        as_is = (a.T_rise_early_C - pred(a.heat_proxy)) ** 2 + \
                (b.T_rise_early_C - pred(b.heat_proxy)) ** 2
        swapped = (a.T_rise_early_C - pred(b.heat_proxy)) ** 2 + \
                  (b.T_rise_early_C - pred(a.heat_proxy)) ** 2
        out.append({
            "batch_date": d,
            "ch15_policy": a.policy_canonical, "ch16_policy": b.policy_canonical,
            "same_policy": same_policy,
            "testable": not same_policy,
            "ch15_T_rise_C": a.T_rise_early_C, "ch16_T_rise_C": b.T_rise_early_C,
            "sse_as_stored": as_is, "sse_if_swapped": swapped,
            "swap_fits_better": bool(swapped < as_is) if not same_policy else None,
            "note": ("undetectable: both channels run the same policy"
                     if same_policy else
                     "policies differ, so the assignment is testable"),
        })
    return pd.DataFrame(out)


def check_cycling_pauses() -> pd.DataFrame:
    """2018-04-12 page: 'Some cells had OCV errors (caused by the internal
    resistance test) that lead to temporary pauses in cycling.' The cells are not
    named. The struct has no wall clock, so a pause is only visible as an
    abnormally long charge time for that cycle -- `summary["chargetime"]` is the
    0-80% SOC duration in minutes and a pause inside the charge inflates it.
    """
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            ct = s["chargetime"]
            base = np.nanmedian(ct)
            excess = ct - base
            # 3 min over this cell's own median is far outside normal scatter
            flagged = np.flatnonzero(np.isfinite(excess) & (excess > 3.0))
            rows.append({
                "batch_date": d, "channel": r.channel,
                "chargetime_median_min": float(base),
                "n_cycles_over_median_plus_3min": int(flagged.size),
                "frac_cycles_flagged": float(flagged.size / len(ct)),
                "worst_excess_min": float(np.nanmax(excess)) if len(excess) else np.nan,
                "worst_excess_cycle": float(s["cycle"][int(np.nanargmax(excess))])
                                      if len(excess) else np.nan,
                "flagged_cycles_first10": ", ".join(
                    str(int(s["cycle"][i])) for i in flagged[:10]),
            })
    return pd.DataFrame(rows)


def check_time_gaps(min_minutes: float = 60.0) -> pd.DataFrame:
    """Locate the computer restarts directly, one row per affected cycle.

    The structs carry no wall clock, but `summary["chargetime"]` is the measured
    0-80% SOC duration for that cycle, and a restart that interrupts a cycle
    inflates it enormously: normal values are 8-17 minutes, whereas the flagged
    cycles reach several hundred minutes. Anything over `min_minutes` is an order
    of magnitude outside the design range and cannot be a charging policy, so it
    marks a real interruption.

    This is a far more specific restart detector than a capacity spike: it sizes
    the gap in minutes, and the 2017-06-30 page's "effectively ... around an 8-hour
    rest" is directly checkable against it.
    """
    rows = []
    for d, recs in _meta().items():
        for r in recs:
            s, _ = _valid_summary(r)
            ct, cyc = s["chargetime"], s["cycle"]
            for i in np.flatnonzero(np.isfinite(ct) & (ct > min_minutes)):
                rows.append({
                    "batch_date": d, "channel": r.channel, "barcode": r.barcode,
                    "cycle": float(cyc[i]),
                    "chargetime_min": float(ct[i]),
                    "gap_hours": float(ct[i] / 60.0),
                    "cell_median_chargetime_min": float(np.nanmedian(ct)),
                    "QD_this_cycle_Ah": float(s["QDischarge"][i]),
                })
    return pd.DataFrame(rows)


def check_chamber_drift() -> pd.DataFrame:
    """2017-05-12 page: 'The temperature control is somewhat inconsistent, leading
    to variability in the baseline chamber temperature.'

    Measured two ways, because they say different things and only one supports the
    page:

    * `between_cell_iqr_C` -- spread across cells at a fixed cycle. On this measure
      2017-05-12 is unremarkable.
    * `batch_median_range_C` -- how far the batch-median Tavg wanders over the run.
      This is the chamber moving under all cells at once, which is what inconsistent
      temperature control actually looks like, and it is where 2017-05-12 stands out.

    The batch median is taken only over cycles where at least half the batch is
    still running, so the trace is not dragged around by the last few survivors.
    """
    rows = []
    for d, recs in _meta().items():
        nmax = max(len(_valid_summary(r)[0]["cycle"]) for r in recs)
        M = np.full((len(recs), nmax), np.nan)
        for i, r in enumerate(recs):
            v = _valid_summary(r)[0]["Tavg"]
            M[i, :len(v)] = v
        alive = np.sum(np.isfinite(M), axis=0) >= max(5, 0.5 * len(recs))
        med = np.nanmedian(M, axis=0)[alive]
        q25, q75 = np.nanpercentile(M, [25, 75], axis=0)
        rows.append({
            "batch_date": d,
            "n_cells": len(recs),
            "n_cycles_half_alive": int(alive.sum()),
            "batch_median_Tavg_min_C": float(med.min()),
            "batch_median_Tavg_max_C": float(med.max()),
            "batch_median_range_C": float(med.max() - med.min()),
            "largest_single_cycle_step_C": float(np.max(np.abs(np.diff(med)))),
            "between_cell_iqr_C": float(np.nanmedian((q75 - q25)[alive])),
        })
    return pd.DataFrame(rows)


def batch_median_tavg(batch_date: str):
    """(cycle, median Tavg) over cycles where >= half the batch is still running."""
    recs = _meta()[batch_date]
    nmax = max(len(_valid_summary(r)[0]["cycle"]) for r in recs)
    M = np.full((len(recs), nmax), np.nan)
    for i, r in enumerate(recs):
        v = _valid_summary(r)[0]["Tavg"]
        M[i, :len(v)] = v
    alive = np.sum(np.isfinite(M), axis=0) >= max(5, 0.5 * len(recs))
    return np.arange(1, nmax + 1)[alive], np.nanmedian(M, axis=0)[alive]


if __name__ == "__main__":
    TABLES.mkdir(exist_ok=True)
    for name, fn in [
        ("cycle_indexing", check_cycle_indexing),
        ("capacity_spikes", check_capacity_spikes),
        ("chargetime", check_chargetime),
        ("internal_resistance", check_ir),
        ("temperature", check_temperature),
        ("eol_criterion", check_eol_criterion),
        ("missing_summary_data", check_missing_summary_data),
        ("chamber_drift", check_chamber_drift),
        ("thermocouple_outliers", check_thermocouple_outliers),
        ("thermocouple_swap", check_thermocouple_swap),
        ("cycling_pauses", check_cycling_pauses),
        ("time_gaps", check_time_gaps),
        ("ir_zero_cycles", check_ir_zero_cycles),
        ("continuation_junction", check_continuation_junction),
    ]:
        df = fn()
        df.to_csv(TABLES / f"{name}.csv", index=False)
        print(f"wrote tables/{name}.csv  ({len(df)} rows)")
