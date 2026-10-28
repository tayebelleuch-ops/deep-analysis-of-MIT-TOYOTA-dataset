"""Stage 1: extract the within-cycle data the v1.0 analysis set does not carry.

Reads the three raw .mat batch structs (mode="r" only, never written) and writes,
into `exploration/extract_out/` (gitignored):

    within_cycle_<batch_date>.h5   the nine within-cycle series + the Vdlin grid
    within_cycle_index.csv         one row per struct cycle: keys, flags, diagnostics
    within_cycle_cells.csv         one row per physical cell: the per-cell metadata
                                   absent from analysis_set_cells.csv

Design decisions, all settled at Stage 0 (`EXTRACTION_PLAN.md`):

* **Keys.** Every row is keyed `(cell_uid, cycle)` in exactly the numbering of
  `analysis_set_cycles.csv`: `cell_uid` is the upper-cased barcode, and `cycle` is the
  segment's own `summary["cycle"]` plus the total cycle count of all preceding segments.
  Cells are resolved through the decoded `channel_id`, never by struct position; the
  position it resolves to is recorded as `source_struct_index` so the resolution is
  auditable (it differs from `channel - 1` for 113 of the 140 rows).
* **Nothing is dropped.** All 114,738 struct cycles get a row, including the 1,179 that
  D2 truncates (`beyond_crossing`) and the 46 zero placeholders (`is_placeholder`).
* **Nothing is masked, imputed, smoothed or repaired.** Bad cycles are flagged in place,
  which is the same choice `REPORT.md` section 6 makes at the summary level.
* **Precision.** float32 for the eight value series, **float64 for `t`**, because `t` is
  the only field whose consecutive *differences* carry a verdict (the non-monotonic-time
  check). Every diagnostic below is computed from the float64 source before conversion,
  so no reported number depends on the narrowing.
* **Determinism.** Cells are written in ascending channel order (not struct order),
  cycles in ascending cycle order, `track_times=False` on every dataset, and no
  timestamp, hostname or version string is written into any output.

Run from the repository root:

    .venv/bin/python -I exploration/extract_within_cycle.py

Then `extract_flags.py` turns the recorded diagnostics into the series-validity columns,
and `extract_checks.py` runs the join checks.
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

NOMINAL_AH = matr.NOMINAL_CAPACITY_AH          # 1.1 Ah
V_CUTOFF = 3.6                                 # charge cutoff, all three batches
CV_V_TOL = 0.005                               # within 5 mV of cutoff counts as CV
REST_I_TOL = 0.01                              # |I| below this C-rate counts as rest
CHUNK_1D = 1 << 16
CHUNK_GRID = (64, 1000)
GZIP = 4

UNITS = {"I": "C-rate", "V": "V", "T": "degC", "Qc": "Ah", "Qd": "Ah", "t": "minutes",
         "Qdlin": "Ah", "Tdlin": "degC", "discharge_dQdV": "Ah/V", "vdlin": "V"}
NATIVE = ("I", "V", "T", "Qc", "Qd", "t")
GRID = ("Qdlin", "Tdlin", "discharge_dQdV")


# ---------------------------------------------------------------------------
# cell resolution: barcode + channel_id only, never struct position
# ---------------------------------------------------------------------------

def resolve() -> tuple[dict, pd.DataFrame]:
    """Map (batch_date, channel) -> the analysis set's key for that struct row.

    Returns `plan`, keyed (batch_date, channel), each value carrying cell_uid, the
    1-based segment index, the cycle offset to add to that segment's own cycle
    numbers, the cell's EOL cycle (NaN when censored) and the struct index the
    channel resolved to; and a per-cell table for `within_cycle_cells.csv`.
    """
    inv = pd.read_csv(HERE / "cell_inventory.csv")
    inv = inv[inv.in_struct].copy()
    cells = pd.read_csv(HERE / "analysis_set_cells.csv")
    eol = dict(zip(cells.cell_uid, cells.eol_cycle_80pct_soh))

    meta = {d: {r.channel: r for r in matr.read_batch_metadata(d)} for d in matr.BATCH_DATES}

    plan, cell_rows = {}, []
    for r in inv.itertuples():
        segs = [s.split(":ch") for s in r.all_segments.split(" | ")]
        offset, seg_desc = 0, []
        for k, (date, ch) in enumerate(segs, start=1):
            ch = int(ch)
            rec = meta[date][ch]                      # resolved via channel_id
            plan[(date, ch)] = {
                "cell_uid": r.cell_uid,
                "segment": k,
                "offset": offset,
                "eol_cycle": float(eol[r.cell_uid]),
                "struct_index": rec.index,
                "n_cycles": rec.n_cycles,
            }
            seg_desc.append(f"{date}:ch{ch}:idx{rec.index}:n{rec.n_cycles}")
            offset += rec.n_cycles
        first_date, first_ch = segs[0][0], int(segs[0][1])
        cell_rows.append({
            "cell_uid": r.cell_uid,
            "batch_date": first_date,
            "channel": first_ch,
            "n_segments": len(segs),
            "segments_resolved": " | ".join(seg_desc),
            "n_cycles_total": offset,
            # per-cell metadata absent from analysis_set_cells.csv
            "policy_underscore": " | ".join(
                meta[d][int(c)].policy for d, c in segs),
            "policy_readable_as_stored": " | ".join(
                meta[d][int(c)].policy_readable for d, c in segs),
            "cycle_life_struct_field": " | ".join(
                f"{meta[d][int(c)].cycle_life_field:g}" for d, c in segs),
        })
    return plan, pd.DataFrame(cell_rows).sort_values(
        ["batch_date", "channel"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# per-cycle diagnostics, all from the float64 source
# ---------------------------------------------------------------------------

def diagnostics(d: dict[str, np.ndarray], vdlin: np.ndarray,
                qd_summary: float, qc_summary: float) -> dict:
    """Scalars describing one cycle's series. No thresholds are applied here --
    these are the measurements the series-validity flags are later derived from,
    recorded so a reader can re-derive any flag without re-reading the .mat files."""
    t, I, V, T = d["t"], d["I"], d["V"], d["T"]
    Qc, Qd = d["Qc"], d["Qd"]
    n = t.size
    o = {"n_samples": n}

    dt = np.diff(t) if n > 1 else np.array([np.nan])
    o["t_start_min"] = float(t[0]) if n else np.nan
    o["t_end_min"] = float(t[-1]) if n else np.nan
    o["dt_median_s"] = float(np.median(dt) * 60) if n > 1 else np.nan
    o["dt_min_s"] = float(dt.min() * 60) if n > 1 else np.nan
    o["dt_max_s"] = float(dt.max() * 60) if n > 1 else np.nan
    o["n_dt_nonpositive"] = int((dt <= 0).sum()) if n > 1 else 0
    o["n_dt_zero"] = int((dt == 0).sum()) if n > 1 else 0

    for name, a in (("V", V), ("I", I), ("T", T)):
        o[f"{name}_min"] = float(a.min()) if n else np.nan
        o[f"{name}_max"] = float(a.max()) if n else np.nan
    o["Qc_last"] = float(Qc[-1]) if n else np.nan
    o["Qd_last"] = float(Qd[-1]) if n else np.nan
    o["Qc_max"] = float(Qc.max()) if n else np.nan
    o["Qd_max"] = float(Qd.max()) if n else np.nan
    o["n_nan_native"] = int(sum(int(np.isnan(a).sum()) for a in (t, I, V, T, Qc, Qd)))

    # item 2: integrate current over time and compare with the summary
    if n > 1:
        o["Q_dis_integral_Ah"] = float(-np.trapezoid(np.minimum(I, 0.0), t) * NOMINAL_AH / 60.0)
        o["Q_chg_integral_Ah"] = float(np.trapezoid(np.maximum(I, 0.0), t) * NOMINAL_AH / 60.0)
    else:
        o["Q_dis_integral_Ah"] = o["Q_chg_integral_Ah"] = np.nan
    o["QDischarge_summary"] = qd_summary
    o["QCharge_summary"] = qc_summary

    # item 5: CV share of the charge step, keyed to the FIXED 3.6 V cutoff
    chg = I > REST_I_TOL
    if n > 1 and chg.sum() > 1:
        w = np.zeros(n)
        w[1:] += dt / 2.0
        w[:-1] += dt / 2.0
        t_chg = float(w[chg].sum())
        t_cv = float(w[chg & (V >= V_CUTOFF - CV_V_TOL)].sum())
        o["charge_time_min"] = t_chg
        o["cv_time_min"] = t_cv
        o["cv_fraction"] = t_cv / t_chg if t_chg > 0 else np.nan
    else:
        o["charge_time_min"] = o["cv_time_min"] = o["cv_fraction"] = np.nan

    # item 7: rests, and the lowest peak current (a C/10 cycle would show ~0.1 C)
    rest = np.abs(I) < REST_I_TOL
    o["n_rest_samples"] = int(rest.sum())
    if n > 1 and rest.any():
        # longest contiguous rest run, in seconds
        idx = np.flatnonzero(np.diff(np.r_[0, rest.view(np.int8), 0]))
        runs = idx[1::2] - idx[0::2]
        starts, ends = idx[0::2], idx[1::2] - 1
        best = int(np.argmax(runs))
        o["rest_longest_s"] = float((t[min(ends[best], n - 1)] - t[starts[best]]) * 60)
        o["n_rest_runs"] = int(len(runs))
    else:
        o["rest_longest_s"] = 0.0
        o["n_rest_runs"] = 0
    o["I_peak_abs"] = float(np.abs(I).max()) if n else np.nan

    # grid fields
    gl = d["Qdlin"].size
    o["grid_len_raw"] = gl
    if gl == 1000:
        Ql, Tl, dq = d["Qdlin"], d["Tdlin"], d["discharge_dQdV"]
        o["Qdlin_min"] = float(Ql.min()); o["Qdlin_max"] = float(Ql.max())
        o["Qdlin_last"] = float(Ql[-1])          # at Vdlin = 2.0 V
        o["Tdlin_min"] = float(Tl.min()); o["Tdlin_max"] = float(Tl.max())
        o["dQdV_min"] = float(dq.min()); o["dQdV_max"] = float(dq.max())
        o["n_nan_grid"] = int(np.isnan(Ql).sum() + np.isnan(Tl).sum() + np.isnan(dq).sum())
        # item 2: does discharge_dQdV equal d(Qdlin)/d(Vdlin) on the grid?
        num = np.gradient(Ql, vdlin)
        res = num - dq
        o["dqdv_resid_rms"] = float(np.sqrt(np.mean(res ** 2)))
        o["dqdv_resid_max"] = float(np.abs(res).max())
        o["dqdv_num_absmax"] = float(np.abs(num).max())
        # item 2: Tdlin against the native T it was interpolated from
        if n:
            o["Tdlin_excess_over_T_max"] = float(Tl.max() - T.max())
            o["Tdlin_shortfall_under_T_min"] = float(T.min() - Tl.min())
        else:
            o["Tdlin_excess_over_T_max"] = o["Tdlin_shortfall_under_T_min"] = np.nan
    else:
        for k in ("Qdlin_min", "Qdlin_max", "Qdlin_last", "Tdlin_min", "Tdlin_max",
                  "dQdV_min", "dQdV_max", "dqdv_resid_rms", "dqdv_resid_max",
                  "dqdv_num_absmax", "Tdlin_excess_over_T_max",
                  "Tdlin_shortfall_under_T_min"):
            o[k] = np.nan
        o["n_nan_grid"] = 0
    return o


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def extract_batch(date: str, plan: dict, limit: int | None = None) -> list[dict]:
    """Write one batch's HDF5 file; return its index rows, in written order."""
    meta = {r.channel: r for r in matr.read_batch_metadata(date)}
    channels = sorted(meta)                      # deterministic: ascending channel
    if limit:
        channels = channels[:limit]
    n_cycles_total = sum(meta[c].n_cycles for c in channels)
    path = OUT / f"within_cycle_{date}.h5"
    if path.exists():
        path.unlink()

    rows: list[dict] = []
    with h5py.File(path, "w") as out, matr.BatchCycles(date) as bc:
        vdlin = bc.vdlin(0)
        ds = out.create_dataset("vdlin", data=vdlin, track_times=False)
        ds.attrs["units"] = UNITS["vdlin"]
        ds.attrs["note"] = "as read from the struct; identical for every cell of every batch"

        nat = out.create_group("native")
        grid = out.create_group("grid")
        d_nat = {}
        for k in NATIVE:
            dt_ = np.float64 if k == "t" else np.float32
            d_nat[k] = nat.create_dataset(
                k, shape=(0,), maxshape=(None,), dtype=dt_, chunks=(CHUNK_1D,),
                compression="gzip", compression_opts=GZIP, shuffle=True, track_times=False)
            d_nat[k].attrs["units"] = UNITS[k]
        d_off = nat.create_dataset("offset", shape=(n_cycles_total + 1,), dtype=np.int64,
                                   track_times=False)
        d_off.attrs["note"] = "CSR offsets: cycle at row r is [offset[r]:offset[r+1]]"
        d_grid = {}
        for k in GRID:
            d_grid[k] = grid.create_dataset(
                k, shape=(n_cycles_total, 1000), dtype=np.float32, chunks=CHUNK_GRID,
                compression="gzip", compression_opts=GZIP, shuffle=True, track_times=False)
            d_grid[k].attrs["units"] = UNITS[k]
            d_grid[k].attrs["grid"] = "vdlin"
            d_grid[k].attrs["note"] = "NaN on the 46 placeholder rows, whose raw length is 2"

        row_uid = np.empty(n_cycles_total, dtype="S16")
        row_cyc = np.empty(n_cycles_total, dtype=np.int32)

        r0 = 0          # row counter within this batch file
        p0 = 0          # native point counter
        offsets = [0]
        for ch in channels:
            rec = meta[ch]
            key = plan[(date, ch)]
            assert key["struct_index"] == rec.index and key["n_cycles"] == rec.n_cycles
            n = rec.n_cycles
            buf = {k: [] for k in NATIVE}
            gbuf = {k: np.full((n, 1000), np.nan, dtype=np.float32) for k in GRID}
            for j in range(n):
                d = bc.cycle(rec.index, j)
                g = diagnostics(d, vdlin,
                                float(rec.summary["QDischarge"][j]),
                                float(rec.summary["QCharge"][j]))
                for k in NATIVE:
                    buf[k].append(d[k])
                if d["Qdlin"].size == 1000:
                    for k in GRID:
                        gbuf[k][j] = d[k].astype(np.float32)
                cyc = int(rec.summary["cycle"][j]) + key["offset"]
                eol = key["eol_cycle"]
                rows.append({
                    "cell_uid": key["cell_uid"],
                    "cycle": cyc,
                    "segment": key["segment"],
                    "source_batch_date": date,
                    "source_channel": ch,
                    "source_struct_index": rec.index,
                    "source_cycle_index": j,
                    "h5_row": r0 + j,
                    "beyond_crossing": bool(np.isfinite(eol) and cyc > eol),
                    "is_placeholder": bool(d["Qdlin"].size != 1000),
                    "IR_ohm": float(rec.summary["IR"][j]),
                    "QCharge_Ah": float(rec.summary["QCharge"][j]),
                    "QDischarge_Ah": float(rec.summary["QDischarge"][j]),
                    "Tavg_C": float(rec.summary["Tavg"][j]),
                    "Tmax_C": float(rec.summary["Tmax"][j]),
                    "Tmin_C": float(rec.summary["Tmin"][j]),
                    "chargetime_min": float(rec.summary["chargetime"][j]),
                    **g,
                })
                row_uid[r0 + j] = key["cell_uid"].encode()
                row_cyc[r0 + j] = cyc
                offsets.append(offsets[-1] + d["t"].size)

            # one resize + write per cell: bounded memory, no per-cycle I/O
            lens = sum(len(a) for a in buf["t"])
            for k in NATIVE:
                d_nat[k].resize((p0 + lens,))
                d_nat[k][p0:] = np.concatenate(buf[k]).astype(d_nat[k].dtype)
            for k in GRID:
                d_grid[k][r0:r0 + n] = gbuf[k]
            p0 += lens
            r0 += n
            out.flush()
            del buf, gbuf

        assert r0 == n_cycles_total and len(offsets) == n_cycles_total + 1
        d_off[:] = np.asarray(offsets, dtype=np.int64)
        rd = out.create_group("row")
        rd.create_dataset("cell_uid", data=row_uid, track_times=False)
        rd.create_dataset("cycle", data=row_cyc, track_times=False)
    print(f"  {date}: {n_cycles_total:,} cycles, {p0:,} native points, "
          f"{path.stat().st_size/1e9:.3f} GB", flush=True)
    return rows


def main(limit: int | None = None) -> None:
    OUT.mkdir(exist_ok=True)
    plan, cells = resolve()
    print(f"resolved {len(plan)} struct rows -> {len(cells)} physical cells", flush=True)

    all_rows = []
    for date in matr.BATCH_DATES:
        all_rows += extract_batch(date, plan, limit)

    idx = pd.DataFrame(all_rows)
    # deterministic row order, independent of how the batches were walked
    idx = idx.sort_values(["source_batch_date", "source_channel", "source_cycle_index"],
                          kind="mergesort").reset_index(drop=True)
    idx.to_csv(OUT / "within_cycle_index_raw.csv", index=False, float_format="%.10g")
    cells.to_csv(OUT / "within_cycle_cells.csv", index=False)
    print(f"index: {len(idx):,} rows x {len(idx.columns)} columns -> "
          f"within_cycle_index_raw.csv", flush=True)
    print("next: exploration/extract_flags.py (series-validity columns), then "
          "exploration/extract_checks.py (join checks)")


if __name__ == "__main__":
    # `--limit N` extracts only the first N channels of each batch. It exists for
    # smoke-testing the writer; a real extract takes no argument.
    lim = None
    if len(sys.argv) > 2 and sys.argv[1] == "--limit":
        lim = int(sys.argv[2])
    main(lim)
