"""The v1.1 per-cycle table, the per-cell table, and conditioning arrays.

Three entry points, all pandas and numpy only:

* :func:`load_cycle_features` -- the per-cycle exogenous variables. The six summary
  series none of the three v1.0 CSVs carries (``IR``, ``QCharge``, ``Tavg``,
  ``Tmax``, ``Tmin``, ``chargetime``), joined to the v1.0 flags and labels, plus
  ``is_series_valid`` and its nine components.
* :func:`load_cell_features` -- ``analysis_set_cells.csv`` widened by the six
  per-cell columns the extraction adds.
* :func:`load_conditioning` -- the policy numbers as arrays aligned to cells, for a
  conditional generative model.

**Where the data comes from.** All of it is read from ``within_cycle_index.csv``,
a 114,738 x 77 CSV, and ``within_cycle_cells.csv``. Neither is an HDF5 file, which
is why v0.2.0 needs no ``h5py``: the six summary series and all nine validity flags
are columns of the index. Only the within-cycle *series themselves* -- the nine
arrays and the ``Vdlin`` grid -- live in HDF5, and those arrive with v0.3.0.

The index is read with ``usecols``, so the 36 columns these functions expose cost
about 26 MB in memory rather than the file's full 72 MB. The other ~41 columns are
per-cycle diagnostics (``dt_median_s``, ``cv_fraction``, ``Qdlin_max`` and so on),
documented in ``exploration/EXTRACTION.md`` section 4 and readable straight from the
file with ``pandas.read_csv(path, usecols=[...])``.

**Two flags, two questions.** ``is_clean_cycle`` (v1.0) judges a cycle's
``QDischarge`` against its neighbours through an 11-cycle rolling median;
``is_series_valid`` (v1.1) judges the integrity of the cycle's own trace. Neither
supersedes the other and they disagree in both directions: on the 113,559
analysis-set rows, 171 are clean but series-invalid and 87 are the reverse. Nothing
here edits any v1.0 file or any v1.0 flag; ``is_series_valid`` is carried alongside.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pathlib import Path

from . import constants as C
from . import _docs
from ._locate import _missing_v11_files, resolve_v11_dir

__all__ = [
    "load_cycle_features",
    "load_cell_features",
    "load_conditioning",
    "series_valid_keys",
    "v11_counts",
]

# The v1.1 tables, cached per resolved directory for the life of the process.
_V11_CACHE = {}  # type: Dict[str, Dict[str, Any]]

#: v1.0 columns joined onto every per-cycle row. ``QD_Ah`` is deliberately not
#: among them: the index's own ``QDischarge_Ah`` is bit-for-bit equal to it on all
#: 113,559 shared rows, and carrying one column under two names invites the reader
#: to wonder which is authoritative.
_V10_CYCLE_COLUMNS = (
    "soh",
    "cycles_to_eol",
    "is_measured_cycle",
    "is_artifact_cycle",
    "is_restart_cycle",
    "is_junction_cycle",
    "is_clean_cycle",
)

#: The five v1.0 flags, held as pandas nullable booleans in the output so that a
#: row v1.0 never judged reads ``<NA>`` rather than a fabricated ``False``.
_V10_FLAGS = (
    "is_measured_cycle",
    "is_artifact_cycle",
    "is_restart_cycle",
    "is_junction_cycle",
    "is_clean_cycle",
)


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def _resolve_v11(data_dir=None, v11_dir=None):
    """Resolve the v1.1 directory, which is usually not the v1.0 one.

    In a clone the two sets live in ``exploration/`` and
    ``exploration/extract_out/``, so one path cannot name both. The rule:

    1. ``v11_dir=`` wins outright, and a wrong one raises rather than falling back.
    2. otherwise, if ``data_dir=`` happens to hold the v1.1 files too -- the
       everything-in-one-folder case -- use it.
    3. otherwise the ordinary lookup order, which finds a clone by itself.

    ``data_dir`` is never *required* to hold the v1.1 files, because it is
    documented package-wide as the directory of the three v1.0 CSVs.
    """
    if v11_dir is not None:
        return resolve_v11_dir(v11_dir)
    if data_dir is not None:
        candidate = Path(data_dir).expanduser().resolve()
        if not _missing_v11_files(candidate, C.V11_REQUIRED_FILES):
            return resolve_v11_dir(candidate)
    return resolve_v11_dir(None)


def _read_v11(data_dir=None, v11_dir=None) -> Dict[str, Any]:
    """Read and cache the two v1.1 CSVs from a verified directory."""
    from .loaders import _read_csv_with  # local: avoids a circular import

    directory, source = _resolve_v11(data_dir, v11_dir)
    key = str(directory)
    if key not in _V11_CACHE:
        index = _read_csv_with(
            directory / C.V11_INDEX_FILE, usecols=list(C.V11_TABLE_COLUMNS)
        )
        # usecols does not fix column order; the file's order is not ours.
        index = index.reindex(columns=list(C.V11_TABLE_COLUMNS))
        _V11_CACHE[key] = {
            "index": index,
            "cells": _read_csv_with(directory / C.V11_CELLS_FILE),
            "data_dir": str(directory),
            "source": source,
        }
    return _V11_CACHE[key]


def _as_bool(frame: "pd.DataFrame", columns) -> None:
    """Coerce flag columns to a real bool dtype, in place.

    The index stores them as the literals ``True``/``False``, which pandas infers as
    bool on both 2.x and 3.x -- but a subset read or a future writer could leave
    them as object, and a flag that is a string is a silent bug: ``"False"`` is
    truthy.
    """
    for name in columns:
        if name in frame.columns and frame[name].dtype != bool:
            frame[name] = (
                frame[name].map({True: True, False: False, "True": True,
                                 "False": False}).astype(bool)
            )


def series_valid_keys(data_dir=None, v11_dir=None) -> "pd.MultiIndex":
    """Return a ``MultiIndex`` of the ``(cell_uid, cycle)`` pairs that pass v1.1.

    Used by :func:`matr_clean.load_cycles` for its ``require_series_valid``
    argument, so that the v1.0 loader can apply the v1.1 flag without taking on the
    v1.1 columns. Cached with the index, so the cost is one read per process.
    """
    index = _read_v11(data_dir, v11_dir)["index"]
    passing = index.loc[index[C.V11_SERIES_FLAG], ["cell_uid", "cycle"]]
    return pd.MultiIndex.from_arrays(
        [passing["cell_uid"], passing["cycle"]], names=["cell_uid", "cycle"]
    )


def v11_counts(data_dir=None, v11_dir=None) -> Dict[str, Any]:
    """Return every v1.1 count this package quotes, computed from the data."""
    return dict(_compute_v11_counts(data_dir, v11_dir))


def _compute_v11_counts(data_dir=None, v11_dir=None) -> Dict[str, Any]:
    from .loaders import _read

    raw11 = _read_v11(data_dir, v11_dir)
    raw10 = _read(data_dir)
    index = raw11["index"]
    cells = raw10["cells"]

    valid = index[C.V11_SERIES_FLAG]
    in_set = index["in_analysis_set"]
    test_uids = set(cells.loc[cells["fold"] == C.TEST_FOLD, "cell_uid"])
    in_test = index["cell_uid"].isin(test_uids)

    merged = index[["cell_uid", "cycle", "in_analysis_set", C.V11_SERIES_FLAG]].merge(
        raw10["cycles"][["cell_uid", "cycle", C.CLEAN_FLAG]],
        on=["cell_uid", "cycle"],
        how="left",
    )
    m_set = merged["in_analysis_set"].to_numpy(dtype=bool)
    m_clean = merged[C.CLEAN_FLAG].fillna(False).to_numpy(dtype=bool)
    m_valid = merged[C.V11_SERIES_FLAG].to_numpy(dtype=bool)

    grid = ~index["series_grid_in_range"]
    default = in_set & valid & ~in_test
    # clean is only defined on analysis-set rows; combine on the merged frame
    default_both = m_set & m_clean & m_valid & ~in_test.to_numpy(dtype=bool)

    out = {
        "v11_struct_cycles": int(len(index)),
        "v11_analysis_cycles": int(in_set.sum()),
        "v11_beyond_crossing": int(index["beyond_crossing"].sum()),
        "v11_placeholders": int(index["is_placeholder"].sum()),
        "v11_cells": int(index["cell_uid"].nunique()),
        "v11_invalid_cycles": int((~valid).sum()),
        "v11_invalid_cells": int(index.loc[~valid, "cell_uid"].nunique()),
        "v11_grid_cycles": int(grid.sum()),
        "v11_grid_cells": int(index.loc[grid, "cell_uid"].nunique()),
        "v11_disputed": int((m_set & m_clean & ~m_valid).sum()),
        "v11_disputed_cells": int(
            merged.loc[m_set & m_clean & ~m_valid, "cell_uid"].nunique()
        ),
        "v11_reverse": int((m_set & ~m_clean & m_valid).sum()),
        "v11_both_invalid": int((m_set & ~m_clean & ~m_valid).sum()),
        "v11_both_valid": int((m_set & m_clean & m_valid).sum()),
        "v11_default_rows": int(default_both.sum()),
        "v11_series_only_rows": int(default.sum()),
        "v11_test_cycles": int((in_set & in_test).sum()),
        "v11_new_columns": len(C.V11_NEW_SERIES_COLUMNS),
        "v11_index_columns": C.V11_INDEX_N_COLUMNS,
        "v11_continuation_cells": len(C.V11_CONTINUATION_CELLS),
    }
    return out


# ---------------------------------------------------------------------------
# the per-cycle table
# ---------------------------------------------------------------------------

@_docs.register
def load_cycle_features(
    variables=None,
    clean: bool = True,
    require_series_valid: bool = True,
    beyond_crossing: bool = False,
    include_test: bool = False,
    data_dir: Optional[str] = None,
    v11_dir: Optional[str] = None,
):
    """Return the per-cycle exogenous table, keyed ``(cell_uid, cycle)``.

    This is what the three v1.0 CSVs could not give you: ``IR_ohm``,
    ``QCharge_Ah``, ``Tavg_C``, ``Tmax_C``, ``Tmin_C`` and ``chargetime_min``, one
    row per cycle, with every v1.0 and v1.1 quality flag attached.

    **All four filtering defaults protect a model.** ``clean=True`` and
    ``require_series_valid=True`` require *both* quality flags,
    ``beyond_crossing=False`` keeps only the published analysis set, and
    ``include_test=False`` drops the held-out cells. Pass
    ``clean=False, require_series_valid=False, beyond_crossing=True,
    include_test=True`` for all 114,738 struct cycles with every flag intact.

    Parameters
    ----------
    variables:
        Which of the seven summary series to return; ``None`` (the default) returns
        all of them. Keys, provenance and every flag column are always present and
        cannot be dropped -- a quality flag you have to ask for is a quality flag
        somebody will forget.
    clean:
        ``True`` (the default) drops rows v1.0 judged unclean
        (``is_clean_cycle == False``). This is the **summary-level** flag: four
        checks on a cycle's ``QDischarge`` relative to its neighbours. It is not
        evidence that the cycle's own trace is usable -- that is
        ``require_series_valid``.

        The flag is defined only on the published analysis set. The
        ``beyond_crossing`` rows carry ``<NA>`` for it, and ``clean=True`` keeps
        them, because v1.0 passed no judgement on them; whether they appear at all
        is governed by ``beyond_crossing=`` alone.
    require_series_valid:
        ``True`` (the default) drops rows failing ``is_series_valid``: the v1.1
        flag, computed from each cycle's own nine series, that no summary-level
        detector can stand in for. It fails on 249 cycles across 97 cells, which
        includes all 46 zero-filled placeholders, the 48 cycles whose interpolated
        ``Qdlin``/``Tdlin``/``dQdV`` leave the physically possible band (reaching
        +1,431 Ah and -4,030 Ah on a 1.1 Ah cell), and the 53-cycle splice run at
        the start of ``EL150800453240``.

        171 of the rows it drops are ``is_clean_cycle == True``, so this argument is
        not redundant with ``clean``; 87 rows run the other way. Nothing here
        changes ``is_clean_cycle`` or any v1.0 file.
    beyond_crossing:
        ``False`` (the default) keeps only the 113,559 rows of the published
        analysis set. ``True`` adds the 1,179 cycles recorded past each cell's
        0.88 Ah crossing, which decision D2 truncates -- all of them 2017-06-30.
        They carry ``<NA>`` for the five v1.0 flags and real values for the v1.1
        ones.
    include_test:
        ``False`` (the default) drops the cycles of cells with ``fold == -1``.
        Those cells are the fixed held-out test set and must not be used for
        training or model selection.
    data_dir:
        Directory holding the three v1.0 CSVs, as everywhere else in this package.
    v11_dir:
        Directory holding ``within_cycle_index.csv`` and
        ``within_cycle_cells.csv``. ``None`` tries ``data_dir`` first, then the
        ordinary lookup order, which in a clone finds ``exploration/extract_out/``
        by itself. The two sets need separate arguments because in a clone they are
        in different folders.

    Returns
    -------
    A ``DataFrame`` with ``(cell_uid, cycle)`` unique. ``cycle`` is the label from
    the analysis set's numbering -- struct index + 1 -- and is **always** kept, so
    the gaps that filtering leaves are visible rather than silent. Row order is the
    index file's own: ascending channel, then ascending cycle.

    Notes
    -----
    Columns, in output order: the nine keys and provenance fields
    (``cell_uid``, ``cycle``, ``segment``, ``source_batch_date``,
    ``source_channel``, ``source_struct_index``, ``h5_row``, ``n_samples``,
    ``grid_len_raw``), the v1.0 labels ``soh`` and ``cycles_to_eol``, the five v1.0
    flags, the four v1.1 status flags, the nine ``is_series_valid`` components, and
    the requested summary series.

    **Use ``source_batch_date``, never ``batch_date``, to say which file a cycle's
    data is in.** Five cells are continued across batches, and ``batch_date`` in
    both v1.0 CSVs is the *first* segment's on every row -- so a segment-2 cycle of
    ``EL150800460514`` says ``2017-05-12`` while its series sit in
    ``within_cycle_2017-06-30.h5``. ``batch_date`` is not returned here for that
    reason; :func:`load_cell_features` carries it for the cell.

    **Dropped cycles leave gaps.** The loader never fills, interpolates, pads or
    renumbers them. ``df.attrs["filters"]`` records exactly what went, with a count
    per reason.

    What is still not here: the nine within-cycle series and the three interpolated
    grid curves (``Qdlin``, ``Tdlin``, ``discharge_dQdV``). They are HDF5-only and
    arrive in v0.3.0.
    """
    from .loaders import _read, _stamp

    raw11 = _read_v11(data_dir, v11_dir)
    raw10 = _read(data_dir)
    index = raw11["index"]
    n_in = len(index)

    if variables is None:
        series = list(C.V11_SERIES_COLUMNS)
    else:
        if isinstance(variables, str):
            variables = (variables,)
        series = list(variables)
        unknown = [name for name in series if name not in C.V11_SERIES_COLUMNS]
        if unknown:
            raise ValueError(
                "unknown variable(s) {0}. Available: {1}".format(
                    ", ".join(repr(u) for u in unknown),
                    ", ".join(C.V11_SERIES_COLUMNS),
                )
            )

    keep = (
        list(C.V11_KEY_COLUMNS)
        + list(C.V11_STATUS_FLAGS)
        + list(C.V11_COMPONENT_FLAGS)
        + series
    )
    out = index[keep].copy()
    _as_bool(out, C.V11_STATUS_FLAGS + C.V11_COMPONENT_FLAGS)

    # Join the v1.0 labels and flags. validate="1:1" is the join proof: every
    # analysis-set row must match exactly one index row and vice versa.
    v10 = raw10["cycles"][["cell_uid", "cycle"] + list(_V10_CYCLE_COLUMNS)]
    out = out.merge(v10, on=["cell_uid", "cycle"], how="left", validate="1:1")
    for name in _V10_FLAGS:
        out[name] = out[name].astype("boolean")

    order = (
        list(C.V11_KEY_COLUMNS)
        + ["soh", "cycles_to_eol"]
        + list(_V10_FLAGS)
        + list(C.V11_STATUS_FLAGS)
        + list(C.V11_COMPONENT_FLAGS)
        + series
    )
    out = out.reindex(columns=order)

    mask = pd.Series(True, index=out.index)
    excluded = []  # type: List[str]

    if not beyond_crossing:
        drop = ~out["in_analysis_set"]
        excluded.append(
            "cycles past the 0.88 Ah crossing (beyond_crossing): {0} rows".format(
                int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    if not include_test:
        test_uids = set(
            raw10["cells"].loc[raw10["cells"]["fold"] == C.TEST_FOLD, "cell_uid"]
        )
        drop = out["cell_uid"].isin(test_uids)
        excluded.append(
            "cycles of held-out test cells (fold == {0}): {1} rows".format(
                C.TEST_FOLD, int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    if clean:
        # "is False", not "is not True": a <NA> row is one v1.0 never judged.
        drop = out[C.CLEAN_FLAG].fillna(True).astype(bool).eq(False)
        excluded.append(
            "cycles v1.0 flagged (is_clean_cycle == False): {0} rows".format(
                int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    if require_series_valid:
        drop = ~out[C.V11_SERIES_FLAG]
        excluded.append(
            "cycles failing is_series_valid: {0} rows "
            "(of which {1} are is_clean_cycle == True)".format(
                int((drop & mask).sum()),
                int((drop & mask & out[C.CLEAN_FLAG].fillna(False)).sum()),
            )
        )
        mask = mask & ~drop

    result = out.loc[mask].copy()
    applied = {
        "variables": tuple(series),
        "clean": clean,
        "require_series_valid": require_series_valid,
        "beyond_crossing": beyond_crossing,
        "include_test": include_test,
    }
    result = _stamp(result, "load_cycle_features", raw10, applied, excluded, n_in)
    result.attrs["filters"]["v11_data_dir"] = raw11["data_dir"]
    result.attrs["filters"]["v11_data_source"] = raw11["source"]
    result.attrs["filters"]["v11_published"] = C.v11_is_published()
    return result


# ---------------------------------------------------------------------------
# the per-cell table
# ---------------------------------------------------------------------------

@_docs.register
def load_cell_features(
    include_test: bool = False,
    data_dir: Optional[str] = None,
    v11_dir: Optional[str] = None,
):
    """Return the cell table widened by the six columns v1.1 adds.

    ``analysis_set_cells.csv``'s 31 columns, left-joined to
    ``within_cycle_cells.csv``'s ``n_segments``, ``segments_resolved``,
    ``n_cycles_total``, ``policy_underscore``, ``policy_readable_as_stored`` and
    ``cycle_life_struct_field``. @@n_cells@@ rows either way; the join is 1:1 on
    ``cell_uid``.

    ``segments_resolved`` is the provenance string that says, per segment, which
    batch file and which **struct index** each channel resolved to -- e.g.
    ``2017-05-12:ch1:idx0:n1189 | 2017-06-30:ch1:idx7:n662``. It is the record that
    cells were addressed through the decoded ``channel_id``, never by row position,
    which differs for 113 of the 140 struct rows.

    Parameters
    ----------
    include_test:
        ``False`` (the default) drops the @@n_test_cells@@ cells with ``fold == -1``.
        This differs from :func:`matr_clean.load_cells`, which keeps them: that is
        deliberately the inventory view of the dataset, while this is a modelling
        view and follows the package's other loaders.
    data_dir, v11_dir:
        As :func:`load_cycle_features`.

    Notes
    -----
    ``n_cycles_total`` counts every struct cycle of the cell, so it exceeds
    ``n_cycles_kept`` by the cycles decision D2 truncates past the 0.88 Ah
    crossing. ``cycle_life_struct_field`` is the struct's own per-segment
    ``cycle_life`` value, reported as stored and **not** used as a label:
    ``eol_cycle_80pct_soh`` is the audited one.

    ``df.attrs["filters"]`` records what was applied.
    """
    from .loaders import _read, _stamp

    raw11 = _read_v11(data_dir, v11_dir)
    raw10 = _read(data_dir)
    cells = raw10["cells"]
    n_in = len(cells)

    extra = raw11["cells"][["cell_uid"] + list(C.V11_CELL_COLUMNS)]
    out = cells.merge(extra, on="cell_uid", how="left", validate="1:1")

    excluded = []  # type: List[str]
    if not include_test:
        mask = out["fold"] != C.TEST_FOLD
        excluded.append(
            "held-out test cells (fold == {0}): {1} cells".format(
                C.TEST_FOLD, int((~mask).sum())
            )
        )
        out = out.loc[mask].copy()

    out = _stamp(
        out, "load_cell_features", raw10, {"include_test": include_test},
        excluded, n_in,
    )
    out.attrs["filters"]["v11_data_dir"] = raw11["data_dir"]
    out.attrs["filters"]["v11_data_source"] = raw11["source"]
    return out


# ---------------------------------------------------------------------------
# conditioning
# ---------------------------------------------------------------------------

#: The default conditioning fields: the charging policy as numbers. ``policy_C1``
#: is the first-step C-rate, ``policy_Q1_pct`` the state of charge it runs to,
#: ``policy_C2`` the second-step rate, ``policy_n_steps`` the number of steps.
CONDITIONING_FIELDS = ("policy_C1", "policy_Q1_pct", "policy_C2", "policy_n_steps")


@_docs.register
def load_conditioning(
    fields=CONDITIONING_FIELDS,
    include_test: bool = False,
    include_cycle_counts: bool = False,
    data_dir: Optional[str] = None,
    v11_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Return per-cell conditioning variables as arrays aligned to ``cell_uid``.

    For a conditional generative model over SOH curves: the charging policy as a
    numeric matrix, plus the batch each cell belongs to, with a row order that
    v0.3.0's ``load_early_window`` will reproduce exactly so the two can be used
    together without a join.

    This reads ``analysis_set_cells.csv`` only, so it works before any v1.1 file is
    present -- unless ``include_cycle_counts=True``, which needs the index.

    Parameters
    ----------
    fields:
        Which numeric per-cell columns to stack into ``X``. The default is the four
        policy numbers.
    include_test:
        ``False`` (the default) drops cells with ``fold == -1``.
    include_cycle_counts:
        ``True`` adds ``n_cycles`` and ``n_series_invalid`` per cell, counted from
        ``within_cycle_index.csv``. Off by default so this function needs no v1.1
        data at all.
    data_dir, v11_dir:
        As :func:`load_cycle_features`. ``v11_dir`` is consulted only when
        ``include_cycle_counts=True``.

    Returns
    -------
    dict with
        ``cell_uid`` (n,) str -- the row index and the alignment contract;
        ``X`` (n, k) float32 -- ``fields`` stacked in the given order;
        ``fields`` tuple -- the column order of ``X``;
        ``batch_date`` (n,) str -- keep this as a model factor: the three batches
        are not exchangeable;
        ``policy_canonical`` (n,) str -- the policy as a label, for grouping;
        ``fold`` (n,) int;
        ``filters`` dict -- the same record ``df.attrs["filters"]`` carries.
        With ``include_cycle_counts``: ``n_cycles`` and ``n_series_invalid``, both
        (n,) int.

    Notes
    -----
    ``X`` is float32 and may contain ``NaN``: a policy number is ``NaN`` wherever
    the struct's policy string does not parse into that field. Check with
    ``np.isnan(X).any(axis=0)`` before fitting a scaler -- this function does not
    impute, exactly as nothing else here does.

    Row order is ``analysis_set_cells.csv``'s published order, filtered. That order
    carries no meaning in itself, but it is stable and byte-reproducible, which is
    what makes it usable as an alignment contract.
    """
    from .loaders import _read

    raw10 = _read(data_dir)
    cells = raw10["cells"]
    if include_test:
        frame = cells.copy()
    else:
        frame = cells.loc[cells["fold"] != C.TEST_FOLD].copy()

    if isinstance(fields, str):
        fields = (fields,)
    fields = tuple(fields)
    unknown = [name for name in fields if name not in cells.columns]
    if unknown:
        raise ValueError(
            "unknown conditioning field(s) {0}. analysis_set_cells.csv has: "
            "{1}".format(
                ", ".join(repr(u) for u in unknown), ", ".join(map(str, cells.columns))
            )
        )

    matrix = np.column_stack(
        [pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype="float32")
         for name in fields]
    ) if fields else np.empty((len(frame), 0), dtype="float32")

    out = {
        "cell_uid": frame["cell_uid"].to_numpy(dtype=object).astype(str),
        "X": matrix,
        "fields": fields,
        "batch_date": frame["batch_date"].to_numpy(dtype=object).astype(str),
        "policy_canonical": frame["policy_canonical"].to_numpy(
            dtype=object).astype(str),
        "fold": frame["fold"].to_numpy(dtype="int64"),
        "filters": {
            "function": "load_conditioning",
            "applied": {
                "fields": fields,
                "include_test": include_test,
                "include_cycle_counts": include_cycle_counts,
            },
            "excluded": (
                [] if include_test
                else ["held-out test cells (fold == {0}): {1} cells".format(
                    C.TEST_FOLD, int((cells["fold"] == C.TEST_FOLD).sum()))]
            ),
            "n_rows_in": int(len(cells)),
            "n_rows_out": int(len(frame)),
            "data_tag": C.DATA_TAG,
            "data_dir": raw10["data_dir"],
            "data_source": raw10["source"],
        },
    }

    if include_cycle_counts:
        index = _read_v11(data_dir, v11_dir)["index"]
        grouped = index.groupby("cell_uid")
        n_cycles = grouped.size()
        n_invalid = grouped[C.V11_SERIES_FLAG].apply(lambda s: int((~s).sum()))
        uid = frame["cell_uid"]
        out["n_cycles"] = (
            uid.map(n_cycles).fillna(0).to_numpy(dtype="int64")
        )
        out["n_series_invalid"] = (
            uid.map(n_invalid).fillna(0).to_numpy(dtype="int64")
        )

    return out
