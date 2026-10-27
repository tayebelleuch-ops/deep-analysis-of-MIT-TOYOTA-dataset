"""One shared classification of every cell, so the figures, the tables and the
cleaning plan all mark the same cells the same way.

Four mutually exclusive classes, in priority order:

  ok            nothing known against it
  censored      never reached its own test's termination criterion
  page_flagged  a dataset page names a problem with this channel
  data_flagged  the data shows an anomaly that no page mentions

Deliberately mutually exclusive and deliberately *visible*: a flagged cell is
drawn with its own colour AND its own line style in every figure, never hidden
and never merged into the background.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import transcript_issues as ti

TABLES = HERE / "tables"

# status-palette critical / categorical slots 7 and 5; each pairs with a distinct
# dash pattern so class identity never rests on colour alone.
CLASS_STYLE = {
    "ok":           {"color": None,      "ls": "-",   "lw": 0.7, "alpha": 0.40, "z": 1},
    "censored":     {"color": "#d03b3b", "ls": "--",  "lw": 1.3, "alpha": 0.95, "z": 4},
    "page_flagged": {"color": "#6250d6", "ls": "-.",  "lw": 1.1, "alpha": 0.90, "z": 3},
    "data_flagged": {"color": "#e87ba4", "ls": ":",   "lw": 1.3, "alpha": 0.90, "z": 2},
}
CLASS_LABEL = {
    "ok": "no known issue",
    "censored": "censored (never reached criterion)",
    "page_flagged": "flagged on the dataset page",
    "data_flagged": "anomalous in the data, not on any page",
}

# thresholds for `data_flagged`, set from the observed distributions in Step 2
T_RISE_RESID_C = -3.0   # degC below the policy-predicted temperature rise
MIN_SPIKES = 3          # capacity-artifact cycles


def build() -> pd.DataFrame:
    """One row per struct row (batch_date, channel) with its class and reasons."""
    inv = pd.read_csv(HERE / "cell_inventory.csv")
    tc = pd.read_csv(TABLES / "thermocouple_outliers.csv")
    sp = pd.read_csv(TABLES / "capacity_spikes.csv")
    gaps = pd.read_csv(TABLES / "time_gaps.csv")

    spike_n = sp.groupby(["batch_date", "channel"]).size().rename("n_spike_cycles")
    gap_n = gaps.groupby(["batch_date", "channel"]).size().rename("n_time_gaps")

    df = tc[["batch_date", "channel", "barcode", "policy_canonical",
             "T_rise_resid_C", "T_rise_early_C"]].copy()
    df = df.merge(spike_n, on=["batch_date", "channel"], how="left")
    df = df.merge(gap_n, on=["batch_date", "channel"], how="left")
    df[["n_spike_cycles", "n_time_gaps"]] = \
        df[["n_spike_cycles", "n_time_gaps"]].fillna(0).astype(int)

    # censoring is a property of the physical cell; map it onto both segments
    cens = set()
    for _, r in inv[inv["censored"] & inv["in_struct"]].iterrows():
        for seg in str(r["all_segments"]).split(" | "):
            d, ch = seg.split(":ch")
            cens.add((d, int(ch)))
    df["censored"] = [(d, c) in cens for d, c in zip(df.batch_date, df.channel)]

    def page_notes(d, ch):
        return [m for m in ti.cell_issues(d, ch)
                if "terminated before" not in m and "resumed in 2017-06-30" not in m
                and "continuation of a 2017-05-12" not in m]

    df["page_notes"] = [" ; ".join(page_notes(d, c))
                        for d, c in zip(df.batch_date, df.channel)]

    def data_reasons(r):
        out = []
        if np.isfinite(r.T_rise_resid_C) and r.T_rise_resid_C < T_RISE_RESID_C:
            out.append(f"temperature rise {r.T_rise_resid_C:+.1f} degC vs policy "
                       f"(T_rise {r.T_rise_early_C:.2f} degC): poor thermal contact")
        if r.n_spike_cycles >= MIN_SPIKES:
            out.append(f"{r.n_spike_cycles} capacity-artifact cycles")
        return " ; ".join(out)

    df["data_reasons"] = df.apply(data_reasons, axis=1)

    def cls(r):
        if r.censored:
            return "censored"
        if r.page_notes:
            return "page_flagged"
        if r.data_reasons:
            return "data_flagged"
        return "ok"

    df["cell_class"] = df.apply(cls, axis=1)
    return df.sort_values(["batch_date", "channel"]).reset_index(drop=True)


if __name__ == "__main__":
    df = build()
    df.to_csv(TABLES / "cell_flags.csv", index=False)
    print(f"wrote tables/cell_flags.csv ({len(df)} rows)")
    print(df.groupby(["batch_date", "cell_class"]).size().to_string())
    print("\n### data_flagged cells (no page mentions these)")
    g = df[df.cell_class == "data_flagged"]
    print(g[["batch_date", "channel", "barcode", "policy_canonical", "data_reasons"]]
          .to_string(index=False))
