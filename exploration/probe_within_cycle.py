"""Stage 0 inventory: what the structs hold that the analysis set does not carry.

Reads the three raw .mat files (mode="r" only) and reports, from the files rather
than from any documentation page:

1. every field present at the top level, in /batch, in `summary` and in `cycles`,
   so that "not in the analysis set" can be stated against a complete list;
2. dtype and length rule for each within-cycle field;
3. a full census of native array lengths over every cycle of all 140 struct rows,
   which is what sizes the extraction;
4. the `Vdlin` grid -- range, spacing, and whether it is byte-identical for every
   cell of every batch (schema.md checked only the first and last cell of each);
5. observed value ranges per field, from a fixed sample of cycles, for units.

Writes nothing but stdout. Companion to probe_schema.py, which covered the
summary-level schema.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matr

OUT = Path(__file__).resolve().parent / "tables"
SAMPLE_CYCLE_FRACTIONS = (0.0, 0.5, 1.0)   # fixed, so the sample is reproducible


def dump_field_lists() -> dict:
    """Section 1: the complete field inventory, per batch."""
    report = {}
    for date, path in matr.BATCH_FILES.items():
        with h5py.File(path, "r") as f:
            batch = f["batch"]
            summary0 = f[batch["summary"][0, 0]]
            cycles0 = f[batch["cycles"][0, 0]]
            report[date] = {
                "top_level": sorted(f.keys()),
                "batch_fields": sorted(batch.keys()),
                "summary_fields": sorted(summary0.keys()),
                "cycles_fields": sorted(cycles0.keys()),
                "n_rows": int(batch["summary"].shape[0]),
                "batch_field_dtypes": {k: str(batch[k].dtype) for k in sorted(batch.keys())},
                "summary_dtypes": {k: (str(summary0[k].dtype), tuple(summary0[k].shape))
                                   for k in sorted(summary0.keys())},
            }
    return report


def dump_vdlin() -> dict:
    """Section 4: is Vdlin one grid, for every cell of every batch?"""
    out = {}
    ref = None
    for date in matr.BATCH_DATES:
        with matr.BatchCycles(date) as bc:
            grids = []
            for i in range(bc.n_cells):
                grids.append(bc.vdlin(i))
            g = np.array(grids)
            if ref is None:
                ref = g[0]
            d = np.diff(g[0])
            out[date] = {
                "n_cells_checked": int(g.shape[0]),
                "n_points": int(g.shape[1]),
                "first": float(g[0, 0]),
                "last": float(g[0, -1]),
                "step_min": float(d.min()),
                "step_max": float(d.max()),
                "monotone_decreasing": bool((d < 0).all()),
                "identical_within_batch": bool(np.array_equal(g, np.repeat(g[:1], g.shape[0], 0))),
                "bitwise_equal_to_linspace_3.5_2.0_1000":
                    bool(np.array_equal(g[0], np.linspace(3.5, 2.0, 1000))),
                "bitwise_equal_to_linspace_3.6_2.0_1000":
                    bool(np.array_equal(g[0], np.linspace(3.6, 2.0, 1000))),
                "identical_to_first_batch": bool(np.array_equal(g[0], ref)),
                "max_abs_diff_to_first_batch": float(np.abs(g - ref).max()),
            }
    return out


def census() -> "np.ndarray":
    """Section 3: length of every within-cycle array of every cycle of every row.

    Returns a structured array with one row per (batch, struct index, channel,
    cycle index) and the length of each of the nine fields.
    """
    rows = []
    for date in matr.BATCH_DATES:
        meta = matr.read_batch_metadata(date)
        with h5py.File(matr.BATCH_FILES[date], "r") as f:
            batch = f["batch"]
            for rec in meta:
                cyc = f[batch["cycles"][rec.index, 0]]
                n = cyc["I"].shape[0]
                for j in range(n):
                    lens = {}
                    for k in matr.CYCLE_FIELDS:
                        sh = f[cyc[k][j, 0]].shape
                        lens[k] = int(np.prod(sh))
                    rows.append((date, rec.index, rec.channel, rec.barcode.upper(),
                                 j + 1, n, *[lens[k] for k in matr.CYCLE_FIELDS]))
        print(f"  census {date}: {len(rows):,} cycles so far", flush=True)
    dt = [("batch_date", "U10"), ("struct_index", "i4"), ("channel", "i4"),
          ("barcode", "U16"), ("cycle", "i4"), ("n_cycles_row", "i4")] + \
         [(k, "i4") for k in matr.CYCLE_FIELDS]
    return np.array(rows, dtype=dt)


def value_ranges() -> dict:
    """Section 5: observed ranges per field over a fixed sample of cycles."""
    acc = {k: {"min": np.inf, "max": -np.inf, "n_nan": 0, "n_points": 0}
           for k in matr.CYCLE_FIELDS}
    per_batch = {d: {k: {"min": np.inf, "max": -np.inf} for k in matr.CYCLE_FIELDS}
                 for d in matr.BATCH_DATES}
    n_sampled = 0
    for date in matr.BATCH_DATES:
        with matr.BatchCycles(date) as bc:
            for i in range(bc.n_cells):
                n = bc.n_cycles(i)
                idxs = sorted({min(n - 1, max(0, int(round(fr * (n - 1)))))
                               for fr in SAMPLE_CYCLE_FRACTIONS})
                for j in idxs:
                    d = bc.cycle(i, j)
                    n_sampled += 1
                    for k, v in d.items():
                        if v.size == 0:
                            continue
                        acc[k]["min"] = min(acc[k]["min"], float(np.nanmin(v)))
                        acc[k]["max"] = max(acc[k]["max"], float(np.nanmax(v)))
                        acc[k]["n_nan"] += int(np.isnan(v).sum())
                        acc[k]["n_points"] += int(v.size)
                        pb = per_batch[date][k]
                        pb["min"] = min(pb["min"], float(np.nanmin(v)))
                        pb["max"] = max(pb["max"], float(np.nanmax(v)))
    return {"n_cycles_sampled": n_sampled, "overall": acc, "per_batch": per_batch}


def main() -> None:
    print("=" * 78)
    print("1 + 2. FIELD INVENTORY")
    print("=" * 78)
    fields = dump_field_lists()
    print(json.dumps(fields, indent=2, default=str))

    print("=" * 78)
    print("4. Vdlin GRID")
    print("=" * 78)
    print(json.dumps(dump_vdlin(), indent=2))

    print("=" * 78)
    print("5. VALUE RANGES (fixed sample: first / middle / last cycle of each row)")
    print("=" * 78)
    print(json.dumps(value_ranges(), indent=2))

    print("=" * 78)
    print("3. LENGTH CENSUS over every cycle of all 140 struct rows")
    print("=" * 78)
    c = census()
    OUT.mkdir(exist_ok=True)
    np.save(Path(os.environ.get("CENSUS_OUT", ".")) / "census.npy", c)
    print(f"total struct cycles: {len(c):,}")
    native = c["I"]
    for k in ("Qc", "Qd", "T", "V", "t"):
        same = int((c[k] == native).sum())
        print(f"  len({k}) == len(I): {same:,} / {len(c):,}")
    for k in ("Qdlin", "Tdlin", "discharge_dQdV"):
        u = np.unique(c[k])
        print(f"  len({k}) unique values: {u[:5]}{'...' if len(u) > 5 else ''}  "
              f"(n distinct = {len(u)})")
    print()
    print("native length by batch:")
    for d in matr.BATCH_DATES:
        m = c["batch_date"] == d
        v = c["I"][m]
        print(f"  {d}: n_cycles={m.sum():,}  min={v.min()}  p25={np.percentile(v,25):.0f} "
              f" median={np.median(v):.0f}  p75={np.percentile(v,75):.0f}  max={v.max()} "
              f" total_points={v.sum():,}")
    tot_native = int(c["I"].sum())
    print()
    print(f"sum of native lengths per field : {tot_native:,}")
    print(f"native fields (6: I,Qc,Qd,T,V,t): {6*tot_native:,} points")
    print(f"grid fields (3 x 1000)          : {3*1000*len(c):,} points")
    total = 6 * tot_native + 3 * 1000 * len(c)
    print(f"TOTAL float values              : {total:,}")
    print(f"  as float64 raw: {total*8/2**30:.2f} GiB")
    print(f"  as float32 raw: {total*4/2**30:.2f} GiB")


if __name__ == "__main__":
    main()
