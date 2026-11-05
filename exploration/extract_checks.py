"""Stage 1c: verify the extract against the v1.0 analysis set, and that the raw files
were never touched.

Every check either passes or raises. The checks are the ones the brief specifies, plus
HDF5 internal-consistency checks that the brief implies: an index row is worthless if the
offsets it points at are wrong.

Run after `extract_within_cycle.py` and `extract_flags.py`:

    .venv/bin/python -I exploration/extract_checks.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr

OUT = HERE / "extract_out"

# Sizes as published in MANIFEST.md for the v1.0 audit. The raw files are read-only
# inputs; if either size moved, something wrote to them and every result is suspect.
RAW_EXPECTED = {
    "2017-05-12": 3_025_320_241,
    "2017-06-30": 2_007_331_155,
    "2018-04-12": 3_236_690_412,
}
# SHA-256 of the three v1.0 outputs, from MANIFEST.md. They must not move.
V1_HASHES = {
    "analysis_set_cells.csv": "4608880c9f3e96836685aa56383f26f9a060575a3078756ae2c4c51ba43c470e",
    "analysis_set_cycles.csv": "52105f75250a2f6e7acb673a3fa7c04b0e4c3cb6cadedde9fd49972f90e823c1",
    "cell_inventory.csv": "fe3e3115939eb1322acecda81afdf2bec54e505bb43b96a40df6836e6e3514f2",
}

_n_pass = 0


def ck(name: str, ok: bool, detail: object = "") -> None:
    global _n_pass
    if ok:
        _n_pass += 1
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}: {detail}")
        raise AssertionError(f"{name}: {detail}")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main() -> None:
    idx = pd.read_csv(OUT / "within_cycle_index.csv")
    cy = pd.read_csv(HERE / "analysis_set_cycles.csv")

    print("1. the v1.0 files are untouched")
    for name, want in V1_HASHES.items():
        ck(f"{name} SHA-256 unchanged", sha256(HERE / name) == want, "hash moved")

    print("2. the raw .mat files are untouched")
    for date, want in RAW_EXPECTED.items():
        p = matr.BATCH_FILES[date]
        ck(f"{date} size == MANIFEST", p.stat().st_size == want,
           f"{p.stat().st_size} != {want}")
    mt = {d: matr.BATCH_FILES[d].resolve().stat().st_mtime_ns for d in RAW_EXPECTED}
    base = OUT / "raw_mtimes.txt"
    text = "\n".join(f"{d} {mt[d]}" for d in sorted(mt)) + "\n"
    if base.exists():
        ck("raw mtimes unchanged since the first run", base.read_text() == text,
           f"expected\n{base.read_text()}got\n{text}")
    else:
        base.write_text(text)
        print("  ----  raw mtimes recorded for the first time")

    print("3. the join to analysis_set_cycles.csv")
    ck("index row count == 114,738 struct cycles", len(idx) == 114_738, len(idx))
    ck("index (cell_uid, cycle) is unique",
       not idx.duplicated(["cell_uid", "cycle"]).any(),
       int(idx.duplicated(["cell_uid", "cycle"]).sum()))
    ileft = idx.set_index(["cell_uid", "cycle"]).index
    cleft = cy.set_index(["cell_uid", "cycle"]).index
    ck("every analysis-set cycle appears exactly once in the index",
       cleft.isin(ileft).all() and len(cleft) == len(set(cleft)),
       int((~cleft.isin(ileft)).sum()))
    ck("analysis-set rows matched == 113,559", int(idx.in_analysis_set.sum()) == 113_559,
       int(idx.in_analysis_set.sum()))
    extra = idx[~idx.in_analysis_set]
    ck("the extra rows are exactly the beyond_crossing ones",
       bool(extra.beyond_crossing.all()) and int(idx.beyond_crossing.sum()) == len(extra),
       f"{len(extra)} extra, {int(extra.beyond_crossing.sum())} flagged")
    ck("extra rows number 1,179", len(extra) == 1_179, len(extra))
    ck("all 1,179 extra rows are in 2017-06-30",
       set(extra.source_batch_date) == {"2017-06-30"}, set(extra.source_batch_date))

    print("4. the keys are aligned, not merely counted")
    m = idx.merge(cy[["cell_uid", "cycle", "QD_Ah", "is_measured_cycle"]],
                  on=["cell_uid", "cycle"], how="inner")
    ck("QDischarge_Ah == QD_Ah bit-for-bit on all 113,559 shared rows",
       len(m) == 113_559 and bool((m.QDischarge_Ah == m.QD_Ah).all()),
       f"n={len(m)} maxdiff={float((m.QDischarge_Ah - m.QD_Ah).abs().max())}")
    ck("is_placeholder == ~is_measured_cycle on the shared rows",
       bool((m.is_placeholder == ~m.is_measured_cycle).all()),
       int((m.is_placeholder != ~m.is_measured_cycle).sum()))
    ck("placeholders number 46, all 2017-05-12 cycle 1",
       int(idx.is_placeholder.sum()) == 46
       and set(idx.loc[idx.is_placeholder, "source_batch_date"]) == {"2017-05-12"}
       and set(idx.loc[idx.is_placeholder, "source_cycle_index"]) == {0},
       int(idx.is_placeholder.sum()))

    print("5. the HDF5 files are internally consistent")
    tot_pts = 0
    for date in matr.BATCH_DATES:
        p = OUT / f"within_cycle_{date}.h5"
        sub = idx[idx.source_batch_date == date].sort_values("h5_row")
        with h5py.File(p, "r") as f:
            off = f["native/offset"][:]
            ck(f"{date}: offset length == n_cycles + 1", len(off) == len(sub) + 1,
               f"{len(off)} vs {len(sub)+1}")
            ck(f"{date}: offsets non-decreasing", bool((np.diff(off) >= 0).all()), "")
            ck(f"{date}: offset diffs == index n_samples",
               bool((np.diff(off) == sub.n_samples.to_numpy()).all()),
               int((np.diff(off) != sub.n_samples.to_numpy()).sum()))
            for k in ("I", "V", "T", "Qc", "Qd", "t"):
                ck(f"{date}: len(native/{k}) == offset[-1]",
                   f[f"native/{k}"].shape[0] == int(off[-1]), f[f"native/{k}"].shape)
            ck(f"{date}: native/t is float64", f["native/t"].dtype == np.float64,
               f["native/t"].dtype)
            ck(f"{date}: native/V is float32", f["native/V"].dtype == np.float32,
               f["native/V"].dtype)
            for k in ("Qdlin", "Tdlin", "discharge_dQdV"):
                ck(f"{date}: grid/{k} shape == (n_cycles, 1000)",
                   f[f"grid/{k}"].shape == (len(sub), 1000), f[f"grid/{k}"].shape)
            ck(f"{date}: h5_row ordering matches the file",
               bool((f["row/cycle"][:] == sub.cycle.to_numpy()).all()), "")
            ck(f"{date}: vdlin is the stored grid, 3.5 -> 2.0 V",
               f["vdlin"].shape == (1000,) and f["vdlin"][0] == 3.5
               and f["vdlin"][-1] == 2.0, "")
            # the 46 placeholder rows must be NaN in the grid matrices
            ph = sub[sub.is_placeholder].h5_row.to_numpy()
            if len(ph):
                ck(f"{date}: placeholder grid rows are all-NaN",
                   bool(np.isnan(f["grid/Qdlin"][ph]).all()), "")
            tot_pts += int(off[-1])
    ck("total native points == 111,868,738", tot_pts == 111_868_738, tot_pts)

    print("6. a fresh read of the raw files reproduces the stored arrays")
    rng = np.random.default_rng(0)
    checked = 0
    for date in matr.BATCH_DATES:
        sub = idx[idx.source_batch_date == date]
        pick = sub.iloc[rng.choice(len(sub), 20, replace=False)]
        with h5py.File(OUT / f"within_cycle_{date}.h5", "r") as f, \
                matr.BatchCycles(date) as bc:
            off = f["native/offset"][:]
            for _, r in pick.iterrows():
                d = bc.cycle(int(r.source_struct_index), int(r.source_cycle_index))
                a, b = int(off[int(r.h5_row)]), int(off[int(r.h5_row) + 1])
                assert b - a == d["t"].size
                assert np.array_equal(f["native/t"][a:b], d["t"])          # float64: exact
                for k in ("I", "V", "T", "Qc", "Qd"):
                    assert np.array_equal(f[f"native/{k}"][a:b],
                                          d[k].astype(np.float32))
                if d["Qdlin"].size == 1000:
                    for k in ("Qdlin", "Tdlin", "discharge_dQdV"):
                        assert np.array_equal(f[f"grid/{k}"][int(r.h5_row)],
                                              d[k].astype(np.float32))
                checked += 1
    ck(f"{checked} random cycles round-trip exactly", checked == 60, checked)

    print("\n7. SHA-256 of every output")
    lines = []
    for p in sorted(OUT.glob("within_cycle*")):
        h, n = sha256(p), p.stat().st_size
        lines.append(f"{h}  {n:>14,}  {p.name}")
        print(f"  {h}  {n:>14,}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")

    print(f"\nall {_n_pass} checks passed")


if __name__ == "__main__":
    main()
