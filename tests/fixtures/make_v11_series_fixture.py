"""Regenerate the committed within-cycle **series** fixture: two tiny HDF5 files.

``make_v11_fixture.py`` builds the 223-row index fixture the v0.2.x tests use. This
builds a much smaller one *plus the HDF5 files to match it*, so the v0.3.0 series
reader can be tested with no 2.20 GB of data present. The two fixtures are separate
on purpose: the 223-row index and its recorded hashes are left byte-identical.

**What is real, and what is not.** The index rows are a real row subset of the
published ``within_cycle_index.csv``, so every flag, every cycle label, every
``source_batch_date`` and every ``Qdlin_max`` is the published value, and the rows
still join against the repository's hash-pinned ``analysis_set_cycles.csv``. The
grid rows in the HDF5 files are the **real** ``Qdlin`` / ``Tdlin`` /
``discharge_dQdV`` values, so the all-NaN placeholder row and the +48.8 Ah and
+1,430.7 Ah out-of-band rows are the real numbers.

Exactly two columns are rewritten, because they are facts about *this* storage
rather than about the data:

* ``h5_row`` -- renumbered to the fixture files' own compact row numbering;
* ``n_samples`` -- the native series are truncated to the first
  :data:`NATIVE_SAMPLES` samples per cycle (the 2-sample placeholder is kept whole),
  which is what keeps the fixture at tens of KB instead of hundreds. The dtypes, the
  CSR offset structure and the placeholder's literal ``0.0`` samples are preserved
  exactly.

Everything else about the layout mirrors the real files: no root attributes;
``/vdlin`` float64 contiguous; ``/native/offset`` int64 contiguous;
``/native/{I,V,T,Qc,Qd}`` float32 and ``/native/t`` float64 chunked ``(65536,)``
gzip-4 + shuffle; ``/grid/*`` float32 chunked ``(64, 1000)`` gzip-4 + shuffle;
``/row/cycle`` int32 and ``/row/cell_uid`` ``|S16`` contiguous; the same per-dataset
``units`` / ``grid`` / ``note`` attributes. ``track_times=False`` throughout, and
rows are written in a fixed order, so the output is byte-reproducible.

**Cells are written in descending ``cell_uid`` order inside each file**, which is
deliberately *not* the index's canonical cell order. A reader that addressed rows by
position in the cell list rather than by ``h5_row`` would return the wrong cell's
data, and ``tests/test_v11_series.py`` asserts it does not.

What each row is here for:

===============================  ==============================================
row                              why
===============================  ==============================================
``EL150800460514`` cycles 1-3    the cycle-1 placeholder: 2 native ``0.0``
                                 samples, an all-NaN grid row
``EL150800460514`` 1189-1191     the continuation seam: 1189 is segment 1 in
                                 ``2017-05-12``, 1190-1191 are segment 2 in
                                 ``2017-06-30``, while ``batch_date`` says
                                 ``2017-05-12`` on all of them
``EL150800464865`` 11,12,13,15   out-of-band ``Qdlin`` (+48.8 Ah) at cycle 12,
                                 a struct index that is not ``channel - 1``, and
                                 **no cycle 14**, so a request for 11-15 has a
                                 real gap in it
``EL150800460511`` 246,247       ``Qdlin`` reaching +1,430.7 Ah at cycle 247,
                                 with **no NaN** -- the proof that the
                                 placeholder failure and the out-of-band failure
                                 are independent
===============================  ==============================================

Run it against a directory holding the published files::

    python tests/fixtures/make_v11_series_fixture.py /path/to/extract_out
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "series"

#: Native samples kept per cycle. The placeholder's 2 are kept whole.
NATIVE_SAMPLES = 16

#: ``(cell_uid, cycle)`` pairs to keep, in no particular order; the writer sorts.
ROWS = (
    ("EL150800460514", 1),
    ("EL150800460514", 2),
    ("EL150800460514", 3),
    ("EL150800460514", 1189),
    ("EL150800460514", 1190),
    ("EL150800460514", 1191),
    ("EL150800464865", 11),
    ("EL150800464865", 12),
    ("EL150800464865", 13),
    ("EL150800464865", 15),
    ("EL150800460511", 246),
    ("EL150800460511", 247),
)

GRID_FIELDS = ("Qdlin", "Tdlin", "discharge_dQdV")
GRID_UNITS = {"Qdlin": "Ah", "Tdlin": "degC", "discharge_dQdV": "Ah/V"}
NATIVE_F32 = ("I", "V", "T", "Qc", "Qd")
NATIVE_UNITS = {
    "I": "C-rate", "V": "V", "T": "degC", "Qc": "Ah", "Qd": "Ah", "t": "minutes",
}
GRID_NOTE = "NaN on the 46 placeholder rows, whose raw length is 2"
OFFSET_NOTE = "CSR offsets: cycle at row r is [offset[r]:offset[r+1]]"
VDLIN_NOTE = "as read from the struct; identical for every cell of every batch"


def main(source: str) -> None:
    import h5py

    src = Path(source).expanduser().resolve()
    OUT.mkdir(parents=True, exist_ok=True)

    index = pd.read_csv(src / "within_cycle_index.csv")
    cells = pd.read_csv(src / "within_cycle_cells.csv")

    wanted = pd.DataFrame(list(ROWS), columns=["cell_uid", "cycle"])
    subset = wanted.merge(index, on=["cell_uid", "cycle"], how="left")
    missing = subset[subset["h5_row"].isna()]
    if len(missing):
        raise SystemExit("not in the index: {0}".format(
            list(zip(missing["cell_uid"], missing["cycle"]))))

    # Descending cell_uid inside each file, ascending cycle inside each cell:
    # deliberately not the index's canonical cell order.
    subset = subset.sort_values(
        ["source_batch_date", "cell_uid", "cycle"],
        ascending=[True, False, True], kind="stable",
    ).reset_index(drop=True)

    new_rows = []
    for date, block in subset.groupby("source_batch_date", sort=True):
        target = OUT / "within_cycle_{0}.h5".format(date)
        src_h5 = src / "within_cycle_{0}.h5".format(date)
        order = block.reset_index(drop=True)
        n = len(order)

        native = {name: [] for name in ("t",) + NATIVE_F32}
        grids = {name: np.empty((n, 1000), dtype=np.float32) for name in GRID_FIELDS}
        uids = np.empty(n, dtype="S16")
        cycles_out = np.empty(n, dtype=np.int32)

        with h5py.File(str(src_h5), "r") as f:
            vdlin = np.asarray(f["vdlin"][:])
            for k, row in order.iterrows():
                r = int(row["h5_row"])
                lo, hi = (int(v) for v in f["native/offset"][r:r + 2])
                take = min(NATIVE_SAMPLES, hi - lo)
                for name in ("t",) + NATIVE_F32:
                    native[name].append(
                        np.asarray(f["native"][name][lo:lo + take], copy=True))
                for name in GRID_FIELDS:
                    grids[name][k, :] = f["grid"][name][r]
                uids[k] = row["cell_uid"].encode("ascii")
                cycles_out[k] = int(row["cycle"])
                new_rows.append((row["cell_uid"], int(row["cycle"]), k, take))

        offsets = np.zeros(n + 1, dtype=np.int64)
        offsets[1:] = np.cumsum([len(a) for a in native["t"]])

        with h5py.File(str(target), "w") as out:
            d = out.create_dataset("vdlin", data=vdlin, dtype="f8",
                                   track_times=False)
            d.attrs["units"] = "V"
            d.attrs["note"] = VDLIN_NOTE
            row_g = out.create_group("row")
            row_g.create_dataset("cycle", data=cycles_out, dtype="i4",
                                 track_times=False)
            row_g.create_dataset("cell_uid", data=uids, dtype="S16",
                                 track_times=False)
            nat = out.create_group("native")
            d = nat.create_dataset("offset", data=offsets, dtype="i8",
                                   track_times=False)
            d.attrs["note"] = OFFSET_NOTE
            for name in ("t",) + NATIVE_F32:
                flat = np.concatenate(native[name]) if n else np.empty(0)
                d = nat.create_dataset(
                    name, data=flat.astype("f8" if name == "t" else "f4"),
                    dtype="f8" if name == "t" else "f4",
                    chunks=(min(65536, max(1, flat.size)),),
                    compression="gzip", compression_opts=4, shuffle=True,
                    track_times=False,
                )
                d.attrs["units"] = NATIVE_UNITS[name]
            grid_g = out.create_group("grid")
            for name in GRID_FIELDS:
                d = grid_g.create_dataset(
                    name, data=grids[name], dtype="f4",
                    chunks=(min(64, n), 1000),
                    compression="gzip", compression_opts=4, shuffle=True,
                    track_times=False,
                )
                d.attrs["grid"] = "vdlin"
                d.attrs["units"] = GRID_UNITS[name]
                d.attrs["note"] = GRID_NOTE
        print("wrote {0}  {1} rows  {2:,} bytes".format(
            target.name, n, target.stat().st_size))

    # Rewrite only h5_row and n_samples; every other column stays published.
    remap = {(u, c): (r, s) for u, c, r, s in new_rows}
    subset["h5_row"] = [remap[(u, c)][0]
                        for u, c in zip(subset["cell_uid"], subset["cycle"])]
    subset["n_samples"] = [remap[(u, c)][1]
                           for u, c in zip(subset["cell_uid"], subset["cycle"])]
    subset = subset.reindex(columns=list(index.columns))
    subset.to_csv(OUT / "within_cycle_index.csv", index=False)
    kept = sorted(set(subset["cell_uid"]))
    cells[cells["cell_uid"].isin(kept)].to_csv(
        OUT / "within_cycle_cells.csv", index=False)

    print("wrote {0} index rows over {1} cells, {2} files".format(
        len(subset), len(kept), subset["source_batch_date"].nunique()))
    print("  placeholders         {0}".format(int(subset["is_placeholder"].sum())))
    print("  series-invalid       {0}".format(int((~subset["is_series_valid"]).sum())))
    print("  grid-range failures  {0}".format(
        int((~subset["series_grid_in_range"]).sum())))
    print("  two-file cells       {0}".format(int(
        subset.groupby("cell_uid")["source_batch_date"].nunique().gt(1).sum())))
    print("  Qdlin max            {0:.1f} Ah".format(subset["Qdlin_max"].max()))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_v11_series_fixture.py /path/to/extract_out")
    main(sys.argv[1])
