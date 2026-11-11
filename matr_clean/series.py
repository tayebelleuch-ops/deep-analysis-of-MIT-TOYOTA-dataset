"""The within-cycle series: arbitrary cycle ranges out of the three HDF5 files.

Three entry points, all of which need the optional ``series`` extra
(``pip install 'matr-clean[series]'``):

* :func:`load_series` -- **the gateway.** Any cells, any cycle range, any mix of the
  six native (ragged) and three grid (1000-point) fields, keyed
  ``(cell_uid, cycle)``.
* :func:`load_vdlin` -- the 1000-point voltage grid, as stored.
* :func:`open_batch` -- an ``h5py.File`` opened ``mode="r"``, for anything the typed
  API does not cover.

**What this module promises, and will not do.**

1. Invalid and placeholder cycles are **returned, masked**. Never interpolated,
   never zero-filled, never silently dropped. A placeholder grid row comes back
   all-NaN because that is what the file holds; an out-of-band row comes back as
   +48.8 Ah because that is what the file holds. ``np.nan_to_num`` on the result
   would convert the 46 missing rows into plausible-looking zeros and would leave
   every impossible value untouched -- the two failures are independent, and
   neither is this loader's to repair.
2. **Gaps are never closed.** ``len(result) == len(cycles)`` always. A requested
   label with no row in the index is a masked position that *keeps its label* and
   gets ``present=False``, so "no such cycle" stays distinguishable from "a bad
   measurement".
3. **Cycle labels are always returned.** ``cycle`` is not optional.
4. Every file is opened ``mode="r"``; nothing is written anywhere.

**Dispatch.** Files are selected from the index's ``source_batch_date``, per row,
never from ``batch_date``. ``batch_date`` in both v1.0 CSVs and in
``within_cycle_cells.csv`` is the *first* segment's on every row, so for the five
continuation cells it names the wrong file for a segment-2 cycle. Cells are
addressed by ``cell_uid`` and located by the index's ``h5_row``; no code path here
computes a row from a channel, a struct index or a position in any array, because
113 of the 140 struct rows have ``source_struct_index + 1 != source_channel``.

**Rolling and expanding windows need no other function.** ``cycles=`` takes any
range, ``start=``/``n=`` take a window directly, and the return carries the labels,
the mask and the gaps -- so one call and a slice is the whole API::

    data = mc.load_series(uid, start=10, n=291)        # labels 10..300, once
    for k in range(100, 301):                          # every expanding prefix
        X, m = data["Qdlin"][:, : k - 9], data["valid"][:, : k - 9]

**Two window conventions.** ``window="labels"`` (the default) indexes cycle labels
as stored; ``window="measured"`` takes each cell's first *n* **non-placeholder**
rows at or after ``start``. ``measured`` *selects* different rows -- it never fills,
clips or interpolates anything, and ``filters["repaired"]`` still says so. The two
differ only where a placeholder or an absent label falls inside the window, and the
only placeholder in the dataset is **label 1 of each of the 46 cells of
2017-05-12**, so from ``start=10`` they are measurably identical: over labels
10..100 they return the same labels, the same mask and the same cells (0 of 12,285
positions differ). Starting at label 1, ``labels`` masks 93 positions across 48 of
135 cells where ``measured`` masks 48 across 18. ``labels`` is the default because
it is the convention in which a label is the same physical cycle in every batch,
and the one the paper's dQ(100-10) feature is defined in.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import constants as C
from . import _h5
from ._locate import _missing_v11_files, resolve_v11_dir

__all__ = [
    "load_series",
    "load_vdlin",
    "open_batch",
]

#: Default ceiling on a single call's array payload. A request for every field of
#: every cycle of every cell is 4.51 GB; this turns that into a ``MemoryError``
#: naming the figure instead of an OOM kill. ``max_bytes=None`` disables it.
DEFAULT_MAX_BYTES = 2 * 1024 ** 3

#: ``is_clean_cycle`` is returned as int8 with this value where v1.0 never judged
#: the row -- the 1,179 ``beyond_crossing`` cycles have no row in
#: ``analysis_set_cycles.csv``. A fabricated ``False`` there would read as "v1.0
#: found this cycle dirty", which is not what the absence of a row means. The
#: pandas-side loaders use a nullable boolean for the same reason; ``-1`` is the
#: numpy-array analogue of ``<NA>``.
CLEAN_NOT_JUDGED = -1


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------

def _resolve_for(names, data_dir=None, v11_dir=None):
    """Resolve a v1.1 directory that holds *names*, with ``features.py``'s rules.

    Identical precedence to :func:`matr_clean.features._resolve_v11` -- ``v11_dir=``
    outright, then ``data_dir=`` if it happens to hold the v1.1 files, then the
    ordinary lookup order -- but parameterised by *names* so only the files a call
    needs are required, verified and, if absent, downloaded. A caller asking for one
    batch is never told the other two are missing, and never fetches 2.20 GB to
    answer a question about 0.58 GB.
    """
    names = tuple(names)
    if v11_dir is not None:
        return resolve_v11_dir(v11_dir, names=names)
    if data_dir is not None:
        from pathlib import Path

        candidate = Path(data_dir).expanduser().resolve()
        if not _missing_v11_files(candidate, names):
            return resolve_v11_dir(candidate, names=names)
    return resolve_v11_dir(None, names=names)


def _split_fields(fields) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    """``(all, grid, native)`` field names, order preserved, duplicates rejected."""
    if isinstance(fields, str):
        fields = (fields,)
    resolved = tuple(str(f) for f in fields)
    if not resolved:
        raise ValueError("fields= is empty; name at least one field")
    seen = []  # type: List[str]
    for name in resolved:
        if name in seen:
            raise ValueError("fields= names {0!r} twice".format(name))
        seen.append(name)
    known = C.V11_NATIVE_FIELDS + C.V11_GRID_FIELDS
    unknown = [f for f in resolved if f not in known]
    if unknown:
        raise ValueError(
            "unknown field(s) {0}. The nine fields are: {1}.\n"
            "(The grid field is 'discharge_dQdV'; 'dQdV' is an index column name, "
            "not a field.)".format(
                ", ".join(repr(u) for u in unknown), ", ".join(known)
            )
        )
    grid = tuple(f for f in resolved if f in C.V11_GRID_FIELDS)
    native = tuple(f for f in resolved if f in C.V11_NATIVE_FIELDS)
    return resolved, grid, native


def _canonical_cells(cells_v10: "pd.DataFrame", cell, include_test: bool,
                     available):
    """The requested cells, in ``analysis_set_cells.csv`` row order.

    That order -- ascending ``batch_date``, then ascending ``channel`` -- is the
    alignment contract: it is measurably the order the index's cells first appear
    in, and it is the order :func:`matr_clean.load_conditioning` returns, so the two
    line up row for row with no join.

    *available* is the set of cells the resolved index actually holds. ``cell=None``
    means **those** cells, not every cell of ``analysis_set_cells.csv``: a caller
    with one batch file on disk, or a partial index, must not be handed 89 rows of
    nothing. A cell named explicitly but absent from the index raises, because a
    silently all-masked cell is worse than an error.
    """
    order = list(cells_v10["cell_uid"])
    known = set(order)
    available = set(available)
    if cell is None:
        wanted = known & available
        if not wanted:
            raise ValueError(
                "the resolved index holds no cell that analysis_set_cells.csv "
                "knows about; is v11_dir= pointing at the right directory?"
            )
    else:
        if isinstance(cell, str):
            cell = [cell]
        wanted = []
        for one in cell:
            text = str(one)
            if text in wanted:
                continue
            wanted.append(text)
        unknown = [u for u in wanted if u not in known]
        if unknown:
            raise ValueError(
                "unknown cell_uid(s): {0}. There are {1} cells; "
                "load_cell_features() lists them.".format(
                    ", ".join(repr(u) for u in unknown), len(order)
                )
            )
        absent = [u for u in wanted if u not in available]
        if absent:
            raise ValueError(
                "the resolved index has no rows for: {0}. Those cells exist, but "
                "not in this index -- check v11_dir=, and that beyond_crossing= "
                "has not excluded every row you asked for.".format(
                    ", ".join(repr(u) for u in absent)
                )
            )
        wanted = set(wanted)

    keep = cells_v10["cell_uid"].isin(wanted)
    if not include_test:
        keep = keep & (cells_v10["fold"] != C.TEST_FOLD)
    chosen = cells_v10.loc[keep]
    if len(chosen) == 0:
        raise ValueError(
            "no cells left to read: every requested cell is a held-out test cell "
            "(fold == -1). Pass include_test=True to keep them."
        )
    return chosen.reset_index(drop=True)


def _normalise_cycles(cycles) -> Optional["np.ndarray"]:
    """``None`` (meaning every cycle of each cell) or an explicit int64 label array.

    Accepts an int, a ``range``, a ``slice``, or any sequence. Labels are **cycle
    labels as stored** (``cycle`` = struct index + 1), never row positions and never
    positions in the returned arrays.
    """
    if cycles is None:
        return None
    if isinstance(cycles, slice):
        if cycles.start is None or cycles.stop is None:
            raise ValueError(
                "cycles=slice(...) needs an explicit start and stop; cycle labels "
                "start at 1 and an open slice has no meaning over labels"
            )
        cycles = range(cycles.start, cycles.stop, cycles.step or 1)
    if isinstance(cycles, (int, np.integer)):
        cycles = [int(cycles)]
    labels = np.asarray(list(cycles), dtype=np.int64)
    if labels.size == 0:
        raise ValueError("cycles= is empty; omit it for every cycle of each cell")
    if (labels < 1).any():
        raise ValueError(
            "cycle labels start at 1 (cycle = struct index + 1); got {0}".format(
                sorted(set(labels[labels < 1].tolist()))
            )
        )
    return labels


def _normalise_window(window, cycles, start, n):
    """Validate ``window``/``start``/``n`` and return ``(window, cycles, start, n)``.

    ``start`` is a cycle **label** under both conventions, never an ordinal, and
    ``n`` is a count of returned positions. The rules, and why each one refuses
    rather than guesses:

    * ``start`` and ``n`` come as a pair. One without the other has no window.
    * ``cycles=`` and ``start``/``n`` are mutually exclusive -- two spellings of
      the same request, and no reason to merge them.
    * ``window="measured"`` with an explicit ``cycles=`` raises: an arbitrary label
      set has no meaning under a convention that re-indexes per cell, and quietly
      reinterpreting the labels would be the one failure this module exists to
      avoid.
    * ``window="labels"`` with ``start``/``n`` is exact sugar: it becomes
      ``cycles=range(start, start + n)`` here, so the two spellings share one code
      path and cannot drift apart.
    """
    window = str(window)
    if window not in ("labels", "measured"):
        raise ValueError(
            "window= must be 'labels' (cycle labels as stored, the default) or "
            "'measured' (each cell's first n non-placeholder cycles from start); "
            "got {0!r}".format(window)
        )
    if (start is None) != (n is None):
        raise ValueError(
            "start= and n= come as a pair: start= is the first cycle label of the "
            "window and n= how many positions it has. Got start={0!r}, n={1!r}."
            .format(start, n)
        )
    if start is not None:
        if cycles is not None:
            raise ValueError(
                "pass either cycles= or start=/n=, not both: cycles=range(a, a + k) "
                "and start=a, n=k are the same request under window='labels'."
            )
        start, n = int(start), int(n)
        if start < 1:
            raise ValueError(
                "start= is a cycle label and labels start at 1 "
                "(cycle = struct index + 1); got {0}".format(start)
            )
        if n < 1:
            raise ValueError(
                "n= is a window length and must be >= 1; got {0}".format(n)
            )
    if window == "measured" and cycles is not None:
        raise ValueError(
            "window='measured' re-indexes each cell onto its own non-placeholder "
            "rows, so an explicit cycles= label set has no meaning there. Use "
            "start=/n= for a measured window, or cycles= with window='labels' "
            "(the default) to name labels outright."
        )
    if window == "labels" and start is not None:
        cycles = range(start, start + n)
    return window, cycles, start, n


def _measured_labels(sub, uids, start, n):
    """Per-cell label grid for ``window="measured"``: the first *n* measured rows.

    A row is *measured* when ``is_placeholder`` is false -- the 46 zero-filled
    placeholders are the only rows the dataset has that are not a measurement, and
    all 46 are label 1 of a 2017-05-12 cell. ``start`` floors the labels, ``n``
    caps the count; ``n=None`` means every measured row each cell has.

    A cell with fewer than *n* such rows gets label ``0`` and ``present=False`` in
    its trailing positions -- the same padding the ``cycles=None`` path uses, and
    label 0 cannot be mistaken for a cycle because labels start at 1. Nothing is
    stretched, repeated or interpolated to fill a short cell.
    """
    pool = sub.loc[~sub["is_placeholder"].astype(bool)]
    if start is not None:
        pool = pool.loc[pool["cycle"] >= start]
    per_cell = pool.groupby("cell_uid")["cycle"].apply(
        lambda column: np.sort(column.to_numpy())
    )
    own = [
        np.asarray(per_cell.get(uid, np.empty(0, dtype=np.int64)), dtype=np.int64)
        for uid in uids
    ]
    n_cycles = int(n) if n is not None else max(int(a.size) for a in own)
    if n_cycles == 0:
        raise ValueError(
            "window='measured' left no cycle to read: none of those cells has a "
            "non-placeholder row in the requested range."
        )
    grid = np.zeros((len(uids), n_cycles), dtype=np.int64)
    for i, labels in enumerate(own):
        take = labels[:n_cycles]
        grid[i, : take.size] = take
    return grid, n_cycles


def _runs(rows: "np.ndarray") -> List[Tuple[int, int]]:
    """Split ascending *rows* into maximal contiguous half-open ``(lo, hi)`` spans.

    A cell's rows inside one file are one contiguous block, so a contiguous cycle
    range is one run and one slice. A sparse request -- ``cycles=[10, 100]`` -- is
    two runs of one row each rather than one 91-row read, which is why this exists
    instead of a single ``min()``/``max()`` span.
    """
    out = []  # type: List[Tuple[int, int]]
    if rows.size == 0:
        return out
    start = prev = int(rows[0])
    for value in rows[1:]:
        value = int(value)
        if value == prev + 1:
            prev = value
            continue
        out.append((start, prev + 1))
        start = prev = value
    out.append((start, prev + 1))
    return out


def _bool_or_false(column) -> "np.ndarray":
    """A left-join flag column as a bool array, with missing read as ``False``.

    Missing here means *the row is not in the index at all*, which the caller has
    already recorded in ``present``; this only keeps the flag arrays the same shape.
    Written without ``Series.fillna`` because filling an object column and casting
    is a silent downcast that pandas 2.2 warns about and pandas 3 changes.
    """
    raw = np.asarray(column.to_numpy(), dtype=object)
    out = np.zeros(raw.shape, dtype=bool)
    known = ~pd.isna(raw)
    if known.any():
        out[known] = raw[known].astype(bool)
    return out


def _int_or_zero(column, dtype) -> "np.ndarray":
    """A left-join integer column as *dtype*, with missing read as ``0``."""
    raw = np.asarray(column.to_numpy(), dtype=object)
    out = np.zeros(raw.shape, dtype=dtype)
    known = ~pd.isna(raw)
    if known.any():
        out[known] = raw[known].astype(np.int64).astype(dtype)
    return out


def _str_or_empty(column) -> "np.ndarray":
    """A left-join string column as ``<U10``, with missing read as ``""``."""
    raw = np.asarray(column.to_numpy(), dtype=object)
    out = np.full(raw.shape, "", dtype="U10")
    known = ~pd.isna(raw)
    if known.any():
        out[known] = raw[known].astype(str)
    return out


def _tri_state(column) -> "np.ndarray":
    """A v1.0 flag as int8: 1 True, 0 False, ``-1`` never judged.

    The 1,179 ``beyond_crossing`` cycles have no row in ``analysis_set_cycles.csv``,
    and neither does a cycle label that does not exist. A fabricated ``False`` there
    would read as "v1.0 found this cycle dirty", which is not what the absence of a
    row means, so the third state is kept.
    """
    raw = np.asarray(column.to_numpy(), dtype=object)
    out = np.full(raw.shape, CLEAN_NOT_JUDGED, dtype=np.int8)
    known = ~pd.isna(raw)
    if known.any():
        out[known] = raw[known].astype(bool).astype(np.int8)
    return out


def _estimate_bytes(grid_fields, native_fields, n_cells, n_cycles, n_samples) -> int:
    """The array payload a request would allocate, before any dataset is read."""
    total = len(grid_fields) * n_cells * n_cycles * C.V11_VDLIN_POINTS * 4
    if native_fields:
        samples = int(np.nansum(n_samples))
        for field in native_fields:
            total += samples * (8 if field == "t" else 4)
    return int(total)


# ---------------------------------------------------------------------------
# the gateway
# ---------------------------------------------------------------------------

def load_series(
    cell=None,
    cycles=None,
    fields=C.V11_GRID_FIELDS,
    clean: bool = False,
    require_series_valid: bool = True,
    beyond_crossing: bool = False,
    include_test: bool = False,
    drop_invalid_cells: bool = False,
    max_bytes: Optional[int] = DEFAULT_MAX_BYTES,
    data_dir: Optional[str] = None,
    v11_dir: Optional[str] = None,
    window: str = "labels",
    start: Optional[int] = None,
    n: Optional[int] = None,
) -> Dict[str, Any]:
    """Read within-cycle series for any cells over any cycle range.

    Parameters
    ----------
    cell:
        One ``cell_uid``, a sequence of them, or ``None`` for every cell. Cells are
        returned in ``analysis_set_cells.csv`` row order whatever order you ask in,
        which is the alignment contract with :func:`load_conditioning`.
    cycles:
        ``None`` for every cycle each cell has; otherwise an int, a ``range``, a
        ``slice`` with explicit bounds, or any sequence of **cycle labels** -- the
        ``window="labels"`` convention, which is what this argument has always
        meant. The returned arrays always have ``len(cycles)`` positions, in the
        order given: a label with no row comes back masked, with its label intact.
        Mutually exclusive with ``start``/``n``.
    window:
        ``"labels"`` (the default) or ``"measured"``.

        ``"labels"`` indexes **cycle labels as stored**: ``start=10, n=91`` is
        labels 10..100 for every cell, and a label the index has no row for is a
        masked position that keeps its label.

        ``"measured"`` takes each cell's first ``n`` **non-placeholder** rows at or
        after ``start`` -- literally "the first n measured cycles" when
        ``start=1`` -- so the labels come back per cell. It counts **rows**: a
        label with no row is simply not one of them, so a measured window can span
        a gap in the labels, and the returned ``cycle`` matrix is the only
        statement of what you got. It **selects** rows; it fills, clips and
        interpolates nothing, and ``filters["repaired"]`` still says so. With
        ``cycles=None`` and no ``start`` it is every measured cycle of each cell,
        i.e. the ``cycles=None`` result minus the 46 placeholders. An explicit
        ``cycles=`` is refused under this convention.

        The two differ only where a placeholder or an absent label falls inside
        the window. The only placeholder is label 1 of each of the 46 cells of
        2017-05-12 (37 of the 108 non-test cells) and no cell has an interior
        label gap, so **from start=10 the two are identical**: over labels 10..100
        they return the same labels, the same mask and the same cells, 0 of 12,285
        positions differing. From label 1 they diverge sharply -- see the
        ``drop_invalid_cells`` figures below. Recommended: leave ``window`` alone
        and start at label 10.
    start, n:
        A window, given directly: ``start`` is the first cycle **label** (never an
        ordinal, under either convention) and ``n`` the number of positions.
        They come as a pair, and exclude ``cycles=``. Under ``window="labels"``,
        ``start=a, n=k`` is exact sugar for ``cycles=range(a, a + k)``. Under
        ``window="measured"`` it is the only way to bound the window, and a cell
        with fewer than ``n`` measured rows from ``start`` gets label ``0`` with
        ``present=False`` in its trailing positions.
    fields:
        Any mix of the six native fields ``t, I, V, T, Qc, Qd`` (ragged, returned as
        nested lists) and the three grid fields ``Qdlin, Tdlin, discharge_dQdV``
        (returned as ``(n_cells, n_cycles, 1000)`` float32). Defaults to the three
        grid fields.
    clean:
        ``True`` also requires the v1.0 ``is_clean_cycle``. Off by default, because
        it is a summary-level judgement about capacity and is not the right question
        to ask of a voltage trace. It **masks**, it does not drop.
    require_series_valid:
        ``True`` (the default) masks every cycle with ``is_series_valid == False``.
        That one predicate covers the 46 placeholders too: ``is_placeholder`` is
        exactly ``~series_present``, so a placeholder is always series-invalid.
    beyond_crossing:
        ``False`` (the default) excludes the 1,179 cycles past the 0.88 Ah crossing
        from the requested set entirely -- structural selection, not masking, the
        same meaning this argument has in :func:`load_cycle_features`.
    include_test:
        ``False`` (the default) drops the 27 held-out cells (``fold == -1``).
    drop_invalid_cells:
        ``True`` removes a whole cell when **any** row in the requested range is
        series-invalid. Off by default, and the measured cost of turning it on
        depends on both the window and the convention. Over labels 1..25, the
        default ``include_test=False`` population of **108** cells:
        ``window="labels"`` costs **39 cells** to recover **80 of 2,700**
        positions, ``window="measured"`` **14 cells** for **44**. Over all 135
        cells (``include_test=True``): **48 for 93**, and **18 for 48**. Over the
        early-cycle window that matters here, labels 10..100, both conventions
        cost **15 of 108** cells (19 of 135) to recover **67 of 9,828** positions
        (71 of 12,285). Masking is almost always the better trade. The dropped
        uids are in ``result["filters"]``.
    max_bytes:
        Ceiling on the array payload, checked before any dataset is read.
        ``None`` disables it. Every field of every cycle of every cell is 4.51 GB.
    data_dir, v11_dir:
        As :func:`load_cycle_features`. Only the batch file(s) this call needs are
        resolved, verified and -- if absent and the record is reachable --
        downloaded.

    Returns
    -------
    dict
        ``cell_uid`` (n_cells,) str, in canonical order; ``cycle``
        (n_cells, n_cycles) int32, the label at each position; ``valid``
        (n_cells, n_cycles) bool, the mask to train on; ``present`` the same shape,
        ``False`` where the index has no such row at all; the raw flags
        ``is_placeholder``, ``is_series_valid``, ``beyond_crossing`` (bool) and
        ``is_clean_cycle`` (int8, **tri-state**: ``1`` clean, ``0`` dirty, ``-1``
        never judged by v1.0 -- *not* "dirty". ``-1`` covers the 1,179
        ``beyond_crossing`` cycles, which have no row in
        ``analysis_set_cycles.csv`` because that file is truncated at each cell's
        80% SOH crossing, and any requested label with no row at all. With the
        default ``beyond_crossing=False`` those cycles are not in the request, so
        ``-1`` then marks only absent labels -- a labels window over 10..100
        returns none. Filter with ``== 1``, never with ``!= 0`` and never by
        truthiness: ``bool(-1)`` is ``True``); ``n_samples``
        (int32); ``segment`` (int8); ``source_batch_date`` (n_cells, n_cycles) str,
        the file each row came from; one entry per requested field; ``vdlin``
        (1000,) float64 if a grid field was asked for; ``fields``, ``field_kind``;
        the per-cell ``batch_date``, ``policy``, ``fold`` and ``cell_flags``; and
        ``filters``, which records the request and what it masked or dropped.

    Notes
    -----
    Nothing is interpolated, zero-filled, clipped or renumbered -- including under
    ``window="measured"``, which chooses which stored rows to return and changes
    no value in any of them. See the module docstring for the four guarantees,
    ``PLAN_v0.3.1.md`` for the window measurements, and ``SPEC_v0.3.md`` for the
    rest.
    """
    from . import features
    from . import loaders

    window, cycles, start, n = _normalise_window(window, cycles, start, n)
    all_fields, grid_fields, native_fields = _split_fields(fields)

    # --- tables ---------------------------------------------------------
    v10 = loaders._read(data_dir)
    index = features._read_v11(data_dir, v11_dir)["index"]
    if not beyond_crossing:
        index = index.loc[~index["beyond_crossing"].astype(bool)]
    chosen = _canonical_cells(
        v10["cells"], cell, include_test, set(index["cell_uid"])
    )
    uids = list(chosen["cell_uid"])

    sub = index.loc[index["cell_uid"].isin(set(uids))]
    if len(sub) == 0:
        raise ValueError(
            "no cycles left to read for those cells. With beyond_crossing=False "
            "only the published analysis set is requestable."
        )

    # --- the request grid ----------------------------------------------
    labels = _normalise_cycles(cycles)
    if window == "measured":
        grid_labels, n_cycles = _measured_labels(sub, uids, start, n)
    elif labels is None:
        per_cell = sub.groupby("cell_uid")["cycle"].apply(
            lambda s: np.sort(s.to_numpy())
        )
        n_cycles = max(int(len(per_cell.get(u, ()))) for u in uids)
        grid_labels = np.zeros((len(uids), n_cycles), dtype=np.int64)
        for i, uid in enumerate(uids):
            own = np.asarray(per_cell.get(uid, np.empty(0, dtype=np.int64)))
            grid_labels[i, : own.size] = own
    else:
        n_cycles = int(labels.size)
        grid_labels = np.tile(labels, (len(uids), 1))

    req = pd.DataFrame(
        {
            "row_i": np.repeat(np.arange(len(uids)), n_cycles),
            "pos_k": np.tile(np.arange(n_cycles), len(uids)),
            "cell_uid": np.repeat(np.asarray(uids, dtype=object), n_cycles),
            "cycle": grid_labels.reshape(-1),
        }
    )
    wanted_cols = [
        "cell_uid", "cycle", "segment", "source_batch_date", "h5_row",
        "n_samples", "is_placeholder", "is_series_valid", "beyond_crossing",
    ]
    req = req.merge(sub[wanted_cols], on=["cell_uid", "cycle"], how="left")
    req = req.sort_values(["row_i", "pos_k"], kind="stable").reset_index(drop=True)

    present = req["h5_row"].notna().to_numpy().reshape(len(uids), n_cycles)

    # --- the v1.0 flag, joined, never fabricated ------------------------
    v10_cycles = v10["cycles"][["cell_uid", "cycle", C.CLEAN_FLAG]]
    joined = req[["cell_uid", "cycle"]].merge(
        v10_cycles, on=["cell_uid", "cycle"], how="left"
    )
    is_clean = _tri_state(joined[C.CLEAN_FLAG]).reshape(len(uids), n_cycles)

    def _flag(name):
        return _bool_or_false(req[name]).reshape(len(uids), n_cycles)

    is_placeholder = _flag("is_placeholder") & present
    is_series_valid = _flag("is_series_valid") & present
    beyond = _flag("beyond_crossing") & present
    n_samples = _int_or_zero(req["n_samples"], np.int32).reshape(
        len(uids), n_cycles)
    segment = _int_or_zero(req["segment"], np.int8).reshape(len(uids), n_cycles)
    src = _str_or_empty(req["source_batch_date"]).reshape(len(uids), n_cycles)

    # --- the mask -------------------------------------------------------
    valid = present.copy()
    if require_series_valid:
        valid = valid & is_series_valid
    if clean:
        valid = valid & (is_clean == 1)

    # --- drop_invalid_cells --------------------------------------------
    dropped = []  # type: List[str]
    if drop_invalid_cells:
        bad = (present & ~is_series_valid).any(axis=1)
        dropped = [uids[i] for i in np.flatnonzero(bad)]
        if bad.all():
            raise ValueError(
                "drop_invalid_cells=True removed every requested cell ({0} of "
                "{0}). Masking is the default for a reason.".format(len(uids))
            )
        keep = ~bad
        uids = [u for u, k in zip(uids, keep) if k]
        chosen = chosen.loc[keep].reset_index(drop=True)
        grid_labels, present, is_placeholder = (
            grid_labels[keep], present[keep], is_placeholder[keep]
        )
        is_series_valid, beyond, is_clean = (
            is_series_valid[keep], beyond[keep], is_clean[keep]
        )
        n_samples, segment, src, valid = (
            n_samples[keep], segment[keep], src[keep], valid[keep]
        )
        req = req.loc[req["row_i"].isin(set(np.flatnonzero(keep).tolist()))]
        remap = {old: new for new, old in enumerate(np.flatnonzero(keep))}
        req = req.assign(row_i=req["row_i"].map(remap))

    n_cells = len(uids)

    # --- the memory guard, before any read ------------------------------
    payload = _estimate_bytes(
        grid_fields, native_fields, n_cells, n_cycles, n_samples[present]
    )
    if max_bytes is not None and payload > max_bytes:
        raise MemoryError(
            "this request would allocate about {0:.2f} GB ({1} cells x {2} cycles "
            "x {3} field(s)), over the max_bytes ceiling of {4:.2f} GB.\n"
            "Loop over cells or over cycle ranges -- load_series is designed for "
            "that -- or raise max_bytes, or pass max_bytes=None to disable the "
            "check.".format(
                payload / 1e9, n_cells, n_cycles, len(all_fields),
                max_bytes / 1e9,
            )
        )

    # --- allocate -------------------------------------------------------
    out = {}  # type: Dict[str, Any]
    for field in grid_fields:
        arr = np.empty((n_cells, n_cycles, C.V11_VDLIN_POINTS), dtype=np.float32)
        arr.fill(np.nan)
        out[field] = arr
    for field in native_fields:
        out[field] = [[None] * n_cycles for _ in range(n_cells)]

    # --- read, one file at a time --------------------------------------
    matched = req.loc[req["h5_row"].notna()]
    dates = sorted(set(matched["source_batch_date"].astype(str)))
    names = tuple(C.V11_REQUIRED_FILES) + _h5.files_for(dates)
    directory, source = _resolve_for(names, data_dir, v11_dir)

    vdlin = None
    for date in dates:
        here = matched.loc[matched["source_batch_date"].astype(str) == date]
        with _h5.open_batch_file(directory, date, "load_series") as handle:
            if vdlin is None and grid_fields:
                vdlin = _h5.vdlin_of(handle)
            for row_i, block in here.groupby("row_i"):
                block = block.sort_values("h5_row", kind="stable")
                rows = block["h5_row"].to_numpy().astype(np.int64)
                positions = block["pos_k"].to_numpy().astype(np.int64)
                i = int(row_i)
                for lo, hi in _runs(rows):
                    take = (rows >= lo) & (rows < hi)
                    local = rows[take] - lo
                    pos = positions[take]
                    for field in grid_fields:
                        out[field][i, pos, :] = _h5.grid_block(
                            handle, field, lo, hi
                        )[local]
                    if native_fields:
                        blocks = _h5.native_blocks(handle, native_fields, lo, hi)
                        for field in native_fields:
                            column = blocks[field]
                            for k, offset in zip(pos, local):
                                out[field][i][int(k)] = column[int(offset)]
                        del blocks

    # --- metadata -------------------------------------------------------
    out["cell_uid"] = np.asarray(uids, dtype="U14")
    out["cycle"] = grid_labels.astype(np.int32)
    out["valid"] = valid
    out["present"] = present
    out["is_placeholder"] = is_placeholder
    out["is_series_valid"] = is_series_valid
    out["beyond_crossing"] = beyond
    out["is_clean_cycle"] = is_clean
    out["n_samples"] = n_samples
    out["segment"] = segment
    out["source_batch_date"] = src
    out["fields"] = all_fields
    out["field_kind"] = dict(
        [(f, "grid") for f in grid_fields] + [(f, "native") for f in native_fields]
    )
    if grid_fields:
        out["vdlin"] = vdlin
    out["batch_date"] = chosen["batch_date"].to_numpy().astype("U10")
    out["policy"] = chosen["policy_canonical"].to_numpy().astype("U16")
    out["fold"] = chosen["fold"].to_numpy().astype(np.int8)
    out["cell_flags"] = dict(
        (name, chosen[name].astype(bool).to_numpy()) for name in C.V11_CELL_FLAGS
    )
    out["filters"] = {
        "source": source,
        "data_dir": str(directory),
        "files_read": list(_h5.files_for(dates)),
        "fields": list(all_fields),
        "window": window,
        "start": None if start is None else int(start),
        "n": None if n is None else int(n),
        "cycles": _describe_request(window, labels, start, n),
        "n_cells": n_cells,
        "n_cycles": n_cycles,
        "n_positions": int(n_cells * n_cycles),
        "n_absent": int((~present).sum()),
        "n_masked": int((present & ~valid).sum()),
        "n_placeholder": int(is_placeholder.sum()),
        "n_series_invalid": int((present & ~is_series_valid).sum()),
        "clean": bool(clean),
        "require_series_valid": bool(require_series_valid),
        "beyond_crossing": bool(beyond_crossing),
        "include_test": bool(include_test),
        "drop_invalid_cells": bool(drop_invalid_cells),
        "cells_dropped": dropped,
        "n_cells_dropped": len(dropped),
        "estimated_bytes": payload,
        "repaired": "nothing: masked in place, never interpolated or zero-filled",
    }
    return out


# ---------------------------------------------------------------------------
# the two small ones
# ---------------------------------------------------------------------------

def _describe_request(window, labels, start, n):
    """What ``filters["cycles"]`` records: the request, in the terms it was made."""
    if window == "measured":
        if start is None:
            return "measured:all"
        return "measured:start={0},n={1}".format(int(start), int(n))
    if labels is None:
        return "all"
    return [int(x) for x in labels]


def load_vdlin(data_dir: Optional[str] = None, v11_dir: Optional[str] = None):
    """Return the 1000-point voltage grid, ``(1000,)`` float64, **as stored**.

    3.5 V down to 2.0 V, identical in all three batch files and identical for every
    cell, which is why it is stored once per file rather than once per cycle. It is
    never reconstructed from ``np.linspace(3.5, 2.0, 1000)``: the two differ in 15
    of 1000 points, by at most 4.440892e-16.

    Reads whichever single batch file is cheapest to resolve -- one already present
    locally if any is, otherwise the smallest. ``Qdlin`` understates discharge
    capacity by a median 31.9 mAh (~3%) and batch-dependently (-36.4 / -49.4 /
    -27.4 mAh) because this grid starts at 3.5 V, below the 3.6 V charge cutoff; a
    normalization fitted on ``Qdlin[-1]`` inherits that batch-correlated bias.
    """
    smallest = min(C.V11_H5_FILES.values(), key=lambda n: C.V11_SIZE_BYTES[n])
    order = [smallest] + [n for n in C.V11_H5_FILES.values() if n != smallest]

    from pathlib import Path

    for name in order:
        try:
            directory, _ = _resolve_for(
                tuple(C.V11_REQUIRED_FILES) + (name,), data_dir, v11_dir
            )
        except Exception:  # noqa: BLE001 - try the next candidate file
            continue
        if not (Path(directory) / name).is_file():
            continue
        date = next(d for d, n in C.V11_H5_FILES.items() if n == name)
        with _h5.open_batch_file(directory, date, "load_vdlin") as handle:
            return _h5.vdlin_of(handle)

    # Nothing local: resolve the smallest, which downloads it if it can.
    date = next(d for d, n in C.V11_H5_FILES.items() if n == smallest)
    directory, _ = _resolve_for(
        tuple(C.V11_REQUIRED_FILES) + (smallest,), data_dir, v11_dir
    )
    with _h5.open_batch_file(directory, date, "load_vdlin") as handle:
        return _h5.vdlin_of(handle)


def open_batch(
    source_batch_date: str,
    data_dir: Optional[str] = None,
    v11_dir: Optional[str] = None,
):
    """Open one batch's HDF5 file ``mode="r"`` and return the ``h5py.File``.

    The escape hatch: everything the typed API does not cover, without giving up the
    lookup order or the hash check. The caller closes it, and it is a context
    manager::

        with mc.open_batch("2017-06-30") as f:
            qdlin = f["grid/Qdlin"][100:110]

    **This takes a ``source_batch_date``, not a ``batch_date``.** The parameter is
    named for the distinction because getting it wrong is the one mistake that
    silently returns the wrong cell's data: ``batch_date`` in both v1.0 CSVs and in
    ``within_cycle_cells.csv`` is the *first* segment's on every row, so for the
    five continuation cells -- ``EL150800460486``, ``EL150800460514``,
    ``EL150800460623``, ``EL150800464865``, ``EL150800464977`` -- it says
    ``2017-05-12`` while their segment-2 cycles live in
    ``within_cycle_2017-06-30.h5``. The index's ``source_batch_date`` column is the
    only correct file selector, and :func:`load_series` uses it per row.

    Row addresses come from the index's ``h5_row``. Do not compute one from a
    channel or a struct index: 113 of the 140 struct rows have
    ``source_struct_index + 1 != source_channel``.
    """
    date = str(source_batch_date)
    if date not in C.V11_H5_FILES:
        raise ValueError(
            "{0!r} is not a source_batch_date of this dataset: {1}".format(
                date, ", ".join(sorted(C.V11_H5_FILES))
            )
        )
    names = tuple(C.V11_REQUIRED_FILES) + (C.V11_H5_FILES[date],)
    directory, _ = _resolve_for(names, data_dir, v11_dir)
    return _h5.open_batch_file(directory, date, "open_batch")
