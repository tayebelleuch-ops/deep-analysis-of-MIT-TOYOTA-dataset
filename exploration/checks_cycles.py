"""Step 2, part B: checks that need the within-cycle arrays.

Read lazily through `matr.BatchCycles` on a sample of cycles per cell rather than
loading whole batches, so this runs in well under a minute and a few hundred MB.
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
from checks import _meta, _runs, REST_I, TABLES

# "C/10" means |I| ~ 0.1 C. Anything whose peak current stays under this is a
# low-rate diagnostic cycle rather than a fast-charge cycle (the policies here all
# peak at >= 1 C on charge and 4 C on discharge).
C10_MAX_I = 1.0

# Upper cutoff potential, fixed for all cells and all current steps (page 01).
V_CUTOFF = 3.6


def cycle_metrics(bc: matr.BatchCycles, ci: int, cyc_idx: int) -> dict | None:
    c = bc.cycle(ci, cyc_idx, ("t", "I", "V"))
    t, I, V = c["t"], c["I"], c["V"]
    if t.size < 5:
        return {"placeholder": True, "n_samples": int(t.size)}
    chg, rest = I > REST_I, np.abs(I) <= REST_I
    vmax = float(np.nanmax(V[chg])) if chg.any() else np.nan
    # The CV phase is where the cell sits at the 3.6 V upper cutoff. Keying the
    # window off this cycle's own max voltage fails on cycles with a small
    # overshoot (vmax 3.606 rather than 3.600), where a 1 mV window lands above
    # the plateau and reports a CV share of zero; 13 cells' last cycles did that.
    # Use the fixed cutoff with a 5 mV tolerance instead.
    cv = chg & (V >= V_CUTOFF - 0.005)
    chg_t = float(t[chg].max() - t[chg].min()) if chg.sum() > 1 else np.nan
    cv_t = float(t[cv].max() - t[cv].min()) if cv.sum() > 1 else 0.0
    rest_s = sorted((float(t[b] - t[a]) * 60 for a, b in _runs(rest) if b > a),
                    reverse=True)
    rest_s = [round(x, 1) for x in rest_s if x > 0.2]
    return {
        "placeholder": False,
        "n_samples": int(t.size),
        "duration_min": float(t[-1]),
        "dt_median_s": float(np.median(np.diff(t)) * 60),
        "I_peak_abs": float(np.nanmax(np.abs(I))),
        "I_peak_charge": float(np.nanmax(I[chg])) if chg.any() else np.nan,
        "I_min_charge": float(np.nanmin(I[chg])) if chg.any() else np.nan,
        "V_max": vmax,
        "charge_min": chg_t,
        "cv_tail_min": cv_t,
        "cv_fraction_of_charge": cv_t / chg_t if chg_t and np.isfinite(chg_t) else np.nan,
        "n_rests": len(rest_s),
        "rest_durations_s": "|".join(f"{x:g}" for x in rest_s),
        "V_noise_mad": float(np.median(np.abs(np.diff(V, 2)))),
    }


def scan(sample_fn, label: str) -> pd.DataFrame:
    """Apply `cycle_metrics` to the cycle indices chosen by `sample_fn(n_cycles)`
    for every cell of every batch."""
    rows = []
    for d, recs in _meta().items():
        with matr.BatchCycles(d) as bc:
            for r in recs:
                n = r.n_cycles
                for tag, cyc_idx in sample_fn(n):
                    m = cycle_metrics(bc, r.index, cyc_idx)
                    if m is None:
                        continue
                    pol = matr.parse_policy(r.policy_readable)
                    rows.append({
                        "batch_date": d, "channel": r.channel, "barcode": r.barcode,
                        "policy_canonical": pol["canonical"], "policy_C1": pol["C1"],
                        "which": tag, "cycle_index": cyc_idx,
                        "cycle_number": cyc_idx + 1, "n_cycles": n, **m,
                    })
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / f"{label}.csv", index=False)
    print(f"wrote tables/{label}.csv ({len(df)} rows)")
    return df


def ends_sample(n):
    """First three and last three cycles -- where an initial or final C/10
    diagnostic cycle would sit."""
    idx = [("first", 0), ("first+1", 1), ("first+2", 2),
           ("last-2", n - 3), ("last-1", n - 2), ("last", n - 1)]
    return [(t, i) for t, i in idx if 0 <= i < n]


def life_sample(n):
    """Cycle 10 and 100 (the pair the paper's DeltaQ feature uses) plus mid-life
    and the last cycle, for the rest / CV / cutoff comparisons."""
    idx = [("cyc10", 9), ("cyc100", 99), ("mid", n // 2), ("last", n - 1)]
    return [(t, i) for t, i in idx if 0 <= i < n]


def check_deltaq_roughness() -> pd.DataFrame:
    """How rough each cell's DeltaQ_{100-10}(V) curve is, relative to its own amplitude.

    This is the measurement that settles 2018-04-12 ch46's "noisy voltage profiles":
    the raw within-cycle voltage trace is dominated by the sampling grid and does not
    single that cell out, but the voltage-domain difference curve -- the thing the
    paper's feature is built on -- does, by a factor of 85 over its batch median.
    """
    rows = []
    for d, recs in _meta().items():
        idx = {r.channel: r.index for r in recs}
        with matr.BatchCycles(d) as bc:
            for r in recs:
                if bc.n_cycles(r.index) <= 100:
                    continue
                a = bc.cycle(r.index, 9, ("Qdlin",))["Qdlin"]
                b = bc.cycle(r.index, 99, ("Qdlin",))["Qdlin"]
                dq = b - a
                amp = float(abs(np.min(dq)))
                noise = float(np.percentile(np.abs(np.diff(dq, 2)), 99))
                rows.append({
                    "batch_date": d, "channel": r.channel, "barcode": r.barcode,
                    "dq_amplitude_Ah": amp, "noise_p99_Ah": noise,
                    "noise_to_signal": noise / amp if amp > 0 else np.nan,
                    "roughness_median": float(np.median(np.abs(np.diff(dq, 2)))),
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    TABLES.mkdir(exist_ok=True)
    ends = scan(ends_sample, "cycle_metrics_ends")
    life = scan(life_sample, "cycle_metrics_life")
    rough = check_deltaq_roughness()
    rough.to_csv(TABLES / "deltaq_roughness.csv", index=False)
    print(f"wrote tables/deltaq_roughness.csv ({len(rough)} rows)")

    print("\n### any low-rate (C/10-like) cycle at the start or end of a test?")
    low = ends[(~ends.placeholder) & (ends.I_peak_abs < C10_MAX_I)]
    print(f"  cells with a cycle whose peak |I| < {C10_MAX_I} C: {len(low)}")
    if len(low):
        print(low[["batch_date", "channel", "which", "I_peak_abs"]].to_string(index=False))
    print("\n  peak |I| at the first and last recorded cycle, by batch:")
    print(ends[~ends.placeholder].groupby(["batch_date", "which"])["I_peak_abs"]
          .agg(["min", "median", "max"]).to_string())
    print("\n  placeholder (2-sample) cycles found:")
    ph = ends[ends.placeholder]
    print(ph.groupby(["batch_date", "which"]).size().to_string() if len(ph) else "  (none)")
