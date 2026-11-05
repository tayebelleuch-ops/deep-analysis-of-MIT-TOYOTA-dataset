"""Regenerate the committed v1.1 test fixture: a small, real subset of the index.

The fixture is **not synthetic**. It is a row subset of the published
``within_cycle_index.csv`` and ``within_cycle_cells.csv``, which means it carries the
real schema, the real dtypes and the real pathological rows, and it still joins
against the real ``analysis_set_cycles.csv`` in the repository. A hand-built CSV
would have needed hand-built v1.0 CSVs to join to, and those are hash-pinned.

Eight cells are kept, chosen so that every regression test has a target:

===========================  ====================================================
cell                         why it is in the fixture
===========================  ====================================================
``EL150800460514``           continuation: segment 1 in 2017-05-12, segment 2 in
                             2017-06-30, so ``batch_date != source_batch_date``.
                             Also carries a cycle-1 placeholder.
``EL150800464977``           the other continuation shape (short segment 2), plus
                             an out-of-band ``Qdlin`` at cycle 12
``EL150800453240``           the 53-cycle splice run (U15): cycles 1-53 corrupt
                             while v1.0 calls 51 of them clean
``EL150800460511``           ``Qdlin`` reaching +1,430.7 Ah at cycle 247 (U13)
``EL150800737364``           ``Qdlin`` reaching -4,030.3 Ah at cycle 368, and
                             ``Tdlin_max`` 523 degC; 2018-04-12 ch 46
``EL150800460605``           2017-06-30, the shortest-lived cell, carries
                             ``beyond_crossing`` rows
``EL150800464865``           a cell whose struct index is not ``channel - 1``
``EL150800737277``           an ordinary 2018-04-12 cell, as the control
===========================  ====================================================

Run it against a directory holding the published files::

    python tests/fixtures/make_v11_fixture.py /path/to/extract_out

The selection is a pure row filter in a fixed order, so the output is
byte-reproducible from the same inputs. Nothing is written back to the source.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent

#: Cells kept, in this order. Row order within a cell is the source file's.
CELLS = (
    "EL150800453240",
    "EL150800460511",
    "EL150800460514",
    "EL150800460605",
    "EL150800464865",
    "EL150800464977",
    "EL150800737277",
    "EL150800737364",
)

#: Cycles kept per cell: a window, so the fixture stays in the low hundreds of
#: rows while still containing the cycle each finding is about.
WINDOWS = {
    "EL150800453240": (1, 60),        # the whole splice run, plus clean tail
    "EL150800460511": (240, 255),     # the +1430 Ah cycle 247
    "EL150800460514": (1, 20),        # the placeholder at cycle 1
    "EL150800460605": (140, 175),     # its beyond_crossing tail
    "EL150800464865": (1, 20),        # placeholder + out-of-band cycle 12
    "EL150800464977": (1, 20),        # placeholder + out-of-band cycle 12
    "EL150800737277": (1, 20),        # the control
    "EL150800737364": (360, 375),     # the -4030 Ah cycle 368
}

#: Plus the continuation seams, which are nowhere near cycle 1.
EXTRA_WINDOWS = {
    "EL150800460514": (1185, 1195),   # segment 1 ends 1189, segment 2 starts 1190
    "EL150800464977": (1222, 1230),   # 1225 / 1226
}


def main(source: str) -> None:
    src = Path(source).expanduser().resolve()
    index = pd.read_csv(src / "within_cycle_index.csv")
    cells = pd.read_csv(src / "within_cycle_cells.csv")

    keep = []
    for uid in CELLS:
        rows = index[index["cell_uid"] == uid]
        if rows.empty:
            raise SystemExit("cell {0} is not in {1}".format(uid, src))
        windows = [WINDOWS[uid]]
        if uid in EXTRA_WINDOWS:
            windows.append(EXTRA_WINDOWS[uid])
        mask = False
        for low, high in windows:
            mask = mask | ((rows["cycle"] >= low) & (rows["cycle"] <= high))
        keep.append(rows[mask])

    subset = pd.concat(keep, ignore_index=True)
    subset.to_csv(HERE / "within_cycle_index.csv", index=False)
    cells[cells["cell_uid"].isin(CELLS)].to_csv(
        HERE / "within_cycle_cells.csv", index=False
    )

    print("wrote {0} index rows, {1} cells".format(len(subset), len(CELLS)))
    print("  placeholders        {0}".format(int(subset["is_placeholder"].sum())))
    print("  series-invalid      {0}".format(int((~subset["is_series_valid"]).sum())))
    print("  grid-range failures {0}".format(
        int((~subset["series_grid_in_range"]).sum())))
    print("  beyond_crossing     {0}".format(int(subset["beyond_crossing"].sum())))
    print("  two-file cells      {0}".format(
        subset.groupby("cell_uid")["source_batch_date"].nunique().gt(1).sum()))
    print("  struct index != channel - 1 on {0} of {1} (cell, segment) pairs".format(
        int((subset["source_struct_index"] != subset["source_channel"] - 1)
            .groupby([subset["cell_uid"], subset["segment"]]).any().sum()),
        subset.groupby(["cell_uid", "segment"]).ngroups))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().splitlines()[0] + "\n\nusage: "
                         "make_v11_fixture.py /path/to/extract_out")
    main(sys.argv[1])
