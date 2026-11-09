"""The only module that imports ``h5py``, and the only one that opens a file.

Everything about the three published HDF5 files that a reader has to know lives
here: how to find them, how to open them, and how to turn a contiguous block of
``h5_row`` values into arrays.

**The layout, as measured** (``exploration/MANIFEST_v1.1.md``, re-verified against
the files on 2026-11-09):

.. code-block:: text

    /vdlin                        (1000,)        float64  contiguous
    /row/cycle                    (n,)           int32    contiguous
    /row/cell_uid                 (n,)           |S16     contiguous
    /native/offset                (n+1,)         int64    contiguous
    /native/{I,V,T,Qc,Qd}         (m,)           float32  chunked (65536,) gzip-4+shuffle
    /native/t                     (m,)           float64  chunked (65536,) gzip-4+shuffle
    /grid/{Qdlin,Tdlin,discharge_dQdV}  (n,1000) float32  chunked (64,1000) gzip-4+shuffle

``n`` is 38,811 / 24,920 / 51,007 and ``m`` is 40,951,666 / 32,094,849 / 38,822,223
for 2017-05-12 / 2017-06-30 / 2018-04-12. The root group carries **no attributes**;
``units`` is on all seven payload datasets, ``grid`` and ``note`` on the three grids,
``note`` on ``/native/offset`` and ``/vdlin``. Only those seven payload datasets are
chunked and compressed; the other four are contiguous and uncompressed.

**One slice per cell per file.** Within one file a cell's ``h5_row`` values are
always a single ascending contiguous block -- measured on all 140 struct rows, and
asserted by ``tests/test_v11_series.py::test_h5_row_blocks_are_contiguous``. That is
what lets every read here be one ``ds[lo:hi]`` against a half-open row range, and
why ``/native/offset`` is read as ``offset[lo:hi + 1]`` rather than whole. Reading
one grid row still decompresses its whole 64-row chunk (256 KB), so a 25-cycle
window costs about one chunk per cell rather than 25 reads.

**Nothing here writes.** Every file is opened ``mode="r"``, and no function in this
module creates, resizes or assigns to a dataset.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import constants as C

__all__ = [
    "require_h5py",
    "open_batch_file",
    "grid_block",
    "native_blocks",
    "vdlin_of",
    "row_keys",
]

#: Raised instead of a bare ``ImportError`` so the message can name the extra.
_IMPORT_HINT = (
    "matr_clean.{0} needs h5py, which is not installed.\n"
    "Install the 'series' extra:\n"
    "    pip install 'matr-clean[series]'\n"
    "h5py>=3.0 is the declared floor; 3.12.1 is the oldest version tested, and\n"
    "3.16.0 is the version that wrote the published files. The files use nothing\n"
    "beyond gzip + shuffle on plain datasets, so any h5py 3.x should read them."
)


def require_h5py(func_name: str = "load_series"):
    """Import and return ``h5py``, or raise a message that names the extra.

    The import is here, inside a function, so that ``import matr_clean`` and every
    v0.2.x entry point keep working with no ``h5py`` installed. *func_name* is the
    public function the caller came in through, so the error names the call rather
    than this private module.
    """
    try:
        import h5py  # noqa: F401  (returned, not used here)
    except ImportError as exc:  # pragma: no cover - exercised with a stubbed import
        raise ImportError(_IMPORT_HINT.format(func_name)) from exc
    return h5py


def files_for(source_batch_dates) -> Tuple[str, ...]:
    """The HDF5 filenames for *source_batch_dates*, in a stable order.

    Keyed by ``source_batch_date`` and never by ``batch_date``: five cells are
    continued across batches, and ``batch_date`` in both v1.0 CSVs is the *first*
    segment's on every row, so it names the wrong file for a segment-2 cycle.
    """
    names = []  # type: List[str]
    for date in sorted(set(str(d) for d in source_batch_dates)):
        if date not in C.V11_H5_FILES:
            raise ValueError(
                "{0!r} is not a source_batch_date of this dataset: {1}".format(
                    date, ", ".join(sorted(C.V11_H5_FILES))
                )
            )
        name = C.V11_H5_FILES[date]
        if name not in names:
            names.append(name)
    return tuple(names)


def open_batch_file(directory, source_batch_date: str, func_name="open_batch"):
    """Open one batch file ``mode="r"``. The caller closes it.

    *directory* is already resolved and hash-verified by
    :func:`matr_clean._locate.resolve_v11_dir`; this function does no lookup of its
    own, so there is exactly one place in the package that decides where data comes
    from.
    """
    h5py = require_h5py(func_name)
    date = str(source_batch_date)
    if date not in C.V11_H5_FILES:
        raise ValueError(
            "{0!r} is not a source_batch_date of this dataset: {1}.\n"
            "Note this takes a *source_batch_date*, not a batch_date: the five "
            "continuation cells\nhave segment-2 cycles in a file their batch_date "
            "does not name.".format(date, ", ".join(sorted(C.V11_H5_FILES)))
        )
    from pathlib import Path

    path = Path(directory) / C.V11_H5_FILES[date]
    return h5py.File(str(path), mode="r")


def grid_block(handle, field: str, lo: int, hi: int) -> "np.ndarray":
    """``(hi - lo, 1000)`` float32 of one grid field, exactly as stored.

    No masking, no repair, no dtype change. Placeholder rows come back all-NaN and
    out-of-band rows come back with their real values, because that is what the
    file holds; deciding what to do about them is the caller's job and
    :func:`matr_clean.load_series` answers it with a mask.
    """
    if field not in C.V11_GRID_FIELDS:
        raise ValueError(
            "{0!r} is not a grid field: {1}".format(
                field, ", ".join(C.V11_GRID_FIELDS)
            )
        )
    return handle["grid"][field][lo:hi]


def native_blocks(handle, fields, lo: int, hi: int) -> Dict[str, List["np.ndarray"]]:
    """Per-cycle 1-D arrays for each native *field* over rows ``lo:hi``.

    The CSR offsets are read as ``offset[lo:hi + 1]`` -- never the whole dataset --
    and each field is then read as **one** contiguous block
    ``ds[offset[lo]:offset[hi]]`` and split. One staging block is live at a time:
    the block is released before the next field is read, which is what keeps a
    full-series read of the largest cell (2,236 cycles, 2.37 M samples) at the
    measured 184 MiB rather than six times its payload.

    Each returned array is a copy, so it owns its data and the staging block can be
    freed. Lengths are ragged by decision 1 of ``SPEC_v0.2.md``: nothing is padded,
    because a pad value would be an invented number.
    """
    for field in fields:
        if field not in C.V11_NATIVE_FIELDS:
            raise ValueError(
                "{0!r} is not a native field: {1}".format(
                    field, ", ".join(C.V11_NATIVE_FIELDS)
                )
            )
    offsets = np.asarray(handle["native/offset"][lo : hi + 1])
    start = int(offsets[0])
    stop = int(offsets[-1])
    local = offsets - start

    out = {}  # type: Dict[str, List[np.ndarray]]
    for field in fields:
        block = handle["native"][field][start:stop]
        rows = []  # type: List[np.ndarray]
        for k in range(hi - lo):
            rows.append(np.array(block[local[k] : local[k + 1]], copy=True))
        out[field] = rows
        del block  # one staging block live at a time
    return out


def vdlin_of(handle) -> "np.ndarray":
    """``(1000,)`` float64 as stored -- never ``np.linspace``.

    The stored grid differs from ``np.linspace(3.5, 2.0, 1000)`` in 15 of its 1000
    points, by at most 4.440892e-16. One ulp is not a reason to reconstruct a value
    that is published.
    """
    return np.asarray(handle["vdlin"][:])


def row_keys(handle, lo: int, hi: int) -> Tuple["np.ndarray", "np.ndarray"]:
    """``(cell_uid, cycle)`` for rows ``lo:hi``, with ``cell_uid`` decoded.

    ``/row/cell_uid`` is stored as fixed-width ``|S16`` bytes, not as a str dtype,
    so it needs decoding; returning the raw bytes would make every comparison
    against a ``cell_uid`` from a CSV fail silently. Used only to verify that the
    index's ``h5_row`` addresses the row it claims.
    """
    uids = np.asarray(handle["row/cell_uid"][lo:hi])
    decoded = np.array([u.decode("ascii") for u in uids], dtype="U14")
    return decoded, np.asarray(handle["row/cycle"][lo:hi])
