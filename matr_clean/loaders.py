"""The loader API: cells, cycles, trajectories, labels, and what the defaults hide.

All five entry points read the same three CSVs, found and hash-verified by
:mod:`matr_clean._locate`. Cells are addressed by ``cell_uid`` (which equals
``barcode``) throughout -- never by row position, because no struct in the source
dataset stores its rows in channel order and the published analysis set preserves
that order.

Decisions D0-D5 that shape this data are recorded in ``exploration/REPORT.md``
section 6; nothing here re-decides any of them.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, NamedTuple, Optional

import pandas as pd

from . import constants as C
from . import _docs
from ._locate import resolve_data_dir

__all__ = [
    "load_cells",
    "load_cycles",
    "load_trajectories",
    "load_labels",
    "describe",
    "counts",
    "Trajectories",
]

# Raw tables, cached per resolved directory for the life of the process.
_CACHE = {}  # type: Dict[str, Dict[str, Any]]


#: The pandas release that both fixed the default CSV float parser and deprecated
#: the argument that used to work around it. Below this, pass the argument; at or
#: above it, do not -- see :func:`_read_csv_kwargs`.
ROUND_TRIP_FIXED_IN = (3, 1)


def _pandas_version() -> tuple:
    """``pandas.__version__`` as a ``(major, minor)`` tuple of ints.

    Tolerates suffixes like ``3.1.0rc0`` and ``2.2.3.dev0+g1234``. An unparsable
    version is treated as older than the fix, which is the safe direction: passing
    the argument to a pandas that does not want it warns, but *not* passing it to a
    pandas that needs it silently corrupts the last bit of every float.
    """
    import re

    match = re.match(r"\s*(\d+)(?:\.(\d+))?", str(pd.__version__))
    if not match:  # pragma: no cover - pandas with no leading digit
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))


def _read_csv_kwargs(version=None) -> Dict[str, Any]:
    """Make float parsing bit-identical on every supported pandas.

    The CSVs carry values that are already correctly rounded decimal
    representations of the float64 they came from, and the loader must read them
    back to the same bits. Three regimes, all measured rather than assumed:

    ============  =====================  ==========================================
    pandas        default CSV parser     ``float_precision="round_trip"``
    ============  =====================  ==========================================
    2.x           **one ulp off**        correct, no warning
    3.0.x         **one ulp off**        correct, no warning
    >= 3.1        correct                **deprecated** -- ``Pandas4Warning``
    ============  =====================  ==========================================

    ``soh = 0.9750086363636363`` reads back as ``0.9750086363636364`` on both
    pandas 2.x and pandas 3.0.x; 3.1 fixed the parser and deprecated the argument in
    the same release. So the argument is passed **below 3.1 and not at or above it**,
    which is the only rule under which every supported version is both bit-exact and
    warning-free.

    An earlier version of this function gated on ``major >= 3``, on the belief that
    pandas 3 had fixed the parser. pandas **3.0** had not: that gate left 3.0.x
    reading one ulp off, which is the bug this replaces.

    *version* overrides the detected version, for tests.
    """
    detected = _pandas_version() if version is None else version
    if detected >= ROUND_TRIP_FIXED_IN:
        return {}
    return {"float_precision": "round_trip"}


_READ_KWARGS = _read_csv_kwargs()


def _read_csv(path):
    return _read_csv_with(path)


def _read_csv_with(path, **kwargs):
    """``pd.read_csv`` with the float-parity keywords, plus anything the caller adds.

    Every CSV this package reads goes through here, so :data:`_READ_KWARGS` applies
    uniformly -- the v1.0 CSVs in :func:`_read` and the v1.1 index and cell table in
    ``features.py``.

    ``features.py`` passes ``usecols=`` here so that the 72.8 MB v1.1 index is never
    materialised in full: only the 36 columns the loader exposes are read.
    """
    try:
        return pd.read_csv(path, **dict(_READ_KWARGS, **kwargs))
    except (TypeError, ValueError):  # pragma: no cover - a pandas that dropped it
        return pd.read_csv(path, **kwargs)


class Trajectories(NamedTuple):
    """What :func:`load_trajectories` returns: a cell table and its cycle table."""

    cells: "pd.DataFrame"
    cycles: "pd.DataFrame"


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def _read(data_dir=None) -> Dict[str, Any]:
    directory, source = resolve_data_dir(data_dir)
    key = str(directory)
    if key not in _CACHE:
        _CACHE[key] = {
            "cells": _read_csv(directory / C.CELLS_FILE),
            "cycles": _read_csv(directory / C.CYCLES_FILE),
            "inventory": _read_csv(directory / C.INVENTORY_FILE),
            "data_dir": str(directory),
            "source": source,
        }
        _docs.fill(_compute_counts(_CACHE[key]))
    return _CACHE[key]


def _compute_counts(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Every number quoted in a docstring or by :func:`describe`, counted here."""
    cells = raw["cells"]
    cycles = raw["cycles"]

    is_test = cells["fold"] == C.TEST_FOLD
    kept_cells = cells.loc[~is_test]
    test_uids = set(cells.loc[is_test, "cell_uid"])
    in_test_cycle = cycles["cell_uid"].isin(test_uids)
    traj_uids = set(cells.loc[cells["use_for_trajectory"], "cell_uid"])
    in_traj_cycle = cycles["cell_uid"].isin(traj_uids)
    clean = cycles[C.CLEAN_FLAG]

    out = {
        # cells
        "n_cells": int(len(cells)),
        "n_labelled": int(cells["has_eol_label"].sum()),
        "n_unlabelled": int((~cells["has_eol_label"]).sum()),
        "n_censored": int(cells["censored"].sum()),
        "n_continuation": int(cells["is_continuation"].sum()),
        "n_traj": int(cells["use_for_trajectory"].sum()),
        "n_traj_labelled": int(
            (cells["use_for_trajectory"] & cells["has_eol_label"]).sum()
        ),
        "n_in_paper": int(cells["in_paper_124"].sum()),
        "n_test_cells": int(is_test.sum()),
        "n_cells_excl_test": int(len(kept_cells)),
        "n_labelled_excl_test": int(kept_cells["has_eol_label"].sum()),
        "n_traj_excl_test": int(kept_cells["use_for_trajectory"].sum()),
        "n_traj_labelled_excl_test": int(
            (kept_cells["use_for_trajectory"] & kept_cells["has_eol_label"]).sum()
        ),
        # cycles
        "n_cycles": int(len(cycles)),
        "n_cycles_clean": int(clean.sum()),
        "n_cycles_flagged": int((~clean).sum()),
        "n_unmeasured": int((~cycles[C.MEASURED_FLAG]).sum()),
        "n_artifact": int(cycles["is_artifact_cycle"].sum()),
        "n_restart": int(cycles["is_restart_cycle"].sum()),
        "n_junction": int(cycles["is_junction_cycle"].sum()),
        "n_test_cycles": int(in_test_cycle.sum()),
        "n_cycles_excl_test": int((~in_test_cycle).sum()),
        "n_cycles_default": int((~in_test_cycle & clean).sum()),
        "n_cycles_flagged_excl_test": int((~in_test_cycle & ~clean).sum()),
        "n_traj_cycles": int(in_traj_cycle.sum()),
        "n_traj_cycles_default": int((in_traj_cycle & ~in_test_cycle & clean).sum()),
        # grouping
        "n_batches": int(cells["batch_date"].nunique()),
        "n_policies": int(cells["policy_canonical"].nunique()),
        "n_policies_excl_test": int(kept_cells["policy_canonical"].nunique()),
        "n_folds": C.N_FOLDS,
        "last_fold": C.N_FOLDS - 1,
    }
    return out


def counts(data_dir=None) -> Dict[str, Any]:
    """Return every count this package quotes, computed from the loaded tables."""
    return dict(_compute_counts(_read(data_dir)))


def _stamp(
    frame: "pd.DataFrame",
    function: str,
    raw: Dict[str, Any],
    applied: Dict[str, Any],
    excluded: List[str],
    n_rows_in: int,
) -> "pd.DataFrame":
    """Attach the filter record every returned frame carries."""
    frame.attrs["filters"] = {
        "function": function,
        "applied": dict(applied),
        "excluded": list(excluded),
        "n_rows_in": int(n_rows_in),
        "n_rows_out": int(len(frame)),
        "data_tag": C.DATA_TAG,
        "data_dir": raw["data_dir"],
        "data_source": raw["source"],
    }
    return frame


# ---------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------

@_docs.register
def load_cells(include_test: bool = True, data_dir: Optional[str] = None):
    """Return the cell table: one row per physical cell, @@n_cells@@ rows.

    This is the inventory view, so **nothing is excluded by default** -- all
    @@n_cells@@ cells come back, including the @@n_test_cells@@ held-out test cells
    (``fold == -1``), the @@n_censored@@ censored cells that carry no label
    (``has_eol_label == False``) and the @@n_continuation@@ continuation cells that
    :func:`load_trajectories` leaves out. Filter with the flag columns, or use
    :func:`load_labels` / :func:`load_trajectories`, which do protect their defaults.

    Parameters
    ----------
    include_test:
        ``True`` (the default) keeps the @@n_test_cells@@ cells with ``fold == -1``.
        ``False`` drops them, leaving @@n_cells_excl_test@@ cells. A cell with
        ``fold == -1`` must not be used for training or model selection.
    data_dir:
        Directory holding the three CSVs. ``None`` uses the lookup order in
        :mod:`matr_clean._locate`.

    Notes
    -----
    Useful columns: ``cell_uid`` (== ``barcode``), ``batch_date``, ``channel``,
    ``policy_canonical``, ``eol_cycle_80pct_soh``, ``eol_basis``, ``has_eol_label``,
    ``censored``, ``is_continuation``, ``use_for_trajectory``, ``in_paper_124``,
    ``fold``. Cells are keyed by ``cell_uid``; row order is the published order and
    carries no meaning.

    ``df.attrs["filters"]`` records what was applied.
    """
    raw = _read(data_dir)
    cells = raw["cells"]
    n_in = len(cells)
    excluded = []  # type: List[str]

    if include_test:
        out = cells.copy()
    else:
        mask = cells["fold"] != C.TEST_FOLD
        out = cells.loc[mask].copy()
        excluded.append(
            "held-out test cells (fold == {0}): {1} cells".format(
                C.TEST_FOLD, int((~mask).sum())
            )
        )

    return _stamp(
        out, "load_cells", raw, {"include_test": include_test}, excluded, n_in
    )


# ---------------------------------------------------------------------------
# cycles
# ---------------------------------------------------------------------------

@_docs.register
def load_cycles(
    clean: bool = True,
    include_test: bool = False,
    require_series_valid: bool = False,
    data_dir: Optional[str] = None,
    v11_dir: Optional[str] = None,
):
    """Return the per-cycle table, truncated at each cell's 80%-SOH crossing.

    The published table is @@n_cycles@@ rows. **Both defaults protect a model**, so
    the default call returns @@n_cycles_default@@ rows: ``clean=True`` keeps only the
    ``is_clean_cycle`` rows, and ``include_test=False`` drops the @@n_test_cycles@@
    cycles belonging to the @@n_test_cells@@ held-out test cells (``fold == -1``).
    Pass ``include_test=True, clean=False`` for the whole published table.

    Only :func:`load_cells` returns everything by default; it is the inventory view,
    one row per cell, and carries no cycles to leak.

    Parameters
    ----------
    clean:
        ``True`` (the default) keeps only ``is_clean_cycle`` rows. That column is the
        conjunction of four orthogonal flags -- ``is_measured_cycle`` and not
        ``is_artifact_cycle``, ``is_restart_cycle`` or ``is_junction_cycle``. The
        @@n_cycles_flagged@@ rows it removes across the whole table break down as
        @@n_unmeasured@@ not measured (2017-05-12's zero-filled cycle-1
        placeholders), @@n_artifact@@ capacity artifacts, @@n_restart@@ cycles
        spanning a test interruption and @@n_junction@@ cycles within two of a
        continuation seam; the categories overlap, so they do not sum to the total.
        Outside the held-out cells it removes @@n_cycles_flagged_excl_test@@ rows.
        ``clean=False`` returns every row with the flags intact -- nothing is masked,
        imputed or smoothed.

        All four flags are judgements about the cycle's ``QDischarge`` value and its
        neighbours, so ``is_clean_cycle`` is a **summary-level** flag: it is not
        evidence that a cycle's voltage, current, temperature or time series is
        usable. See the note below.
    include_test:
        ``False`` (the default) drops the @@n_test_cycles@@ cycles of the
        @@n_test_cells@@ cells with ``fold == -1``, leaving @@n_cycles_excl_test@@
        rows before the clean filter. ``True`` keeps them: @@n_cycles@@ rows, or
        @@n_cycles_clean@@ with ``clean=True``. Those cells are the fixed held-out
        test set and must not be used for training or model selection.
    require_series_valid:
        ``False`` (the default), so **this function behaves exactly as it did in
        v0.1.1**. ``True`` additionally drops cycles failing the v1.1
        ``is_series_valid`` flag, computed from each cycle's own nine within-cycle
        series -- the only thing that catches a broken trace.

        It is a separate argument rather than a third value of ``clean`` because the
        two flags answer different questions and neither implies the other: 171
        analysis-set rows are ``is_clean_cycle == True`` yet series-invalid, and 87
        run the other way. Folding them into one keyword would have made
        ``clean=True`` mean something new to every caller already written.

        ``True`` requires the v1.1 index, so a call that worked with the three CSVs
        alone can start needing ``within_cycle_index.csv``. To get the series
        *columns* as well as the filter, use
        :func:`matr_clean.load_cycle_features`, where both quality flags default on.
    data_dir:
        As :func:`load_cells`.
    v11_dir:
        Where the v1.1 index is, consulted only when ``require_series_valid=True``.
        See :func:`matr_clean.load_cycle_features`.

    Notes
    -----
    Columns: ``cell_uid``, ``batch_date``, ``channel``, ``cycle``, ``segment``,
    ``QD_Ah``, ``soh``, ``cycles_to_eol``, and the five flags. ``soh`` is against the
    1.1 Ah nominal capacity (decision D0), so 80% SOH is 0.88 Ah.

    This table carries the per-cycle *summary* only, and of the struct's own per-cycle
    measurements exactly one: ``QDischarge``, as ``QD_Ah``. Not here, in any of the
    three CSVs: ``IR``, ``QCharge``, ``Tavg``, ``Tmax``, ``Tmin``, ``chargetime``, the
    nine within-cycle series (``t``, ``I``, ``V``, ``Qc``, ``Qd``, ``T``, ``Qdlin``,
    ``Tdlin``, ``discharge_dQdV``) and the ``Vdlin`` voltage grid. So voltage-domain
    quantities (``Qdlin``, ``dQdV``, delta-Q) cannot be computed from this loader; they
    live in the HDF5 files of the v1.1 extraction and arrive in v0.3.0.

    The six summary series **are** available now, from
    :func:`matr_clean.load_cycle_features`, which reads the v1.1 per-cycle index
    rather than these three CSVs.

    ``is_clean_cycle`` is **summary-level and nothing more.** Its four components all
    judge ``QDischarge`` and its neighbours -- an 11-cycle rolling median
    (``is_artifact_cycle``), ``chargetime`` (``is_restart_cycle``), distance to a
    continuation seam (``is_junction_cycle``). None looks inside a cycle, so a clean
    cycle can still carry a broken voltage, current, temperature or time trace. **Do
    not use it to select cycles for voltage-domain or time-series work.** Use
    ``is_series_valid`` for that -- ``require_series_valid=True`` here, or
    :func:`matr_clean.load_cycle_features`, which applies it by default.
    ``is_clean_cycle`` does not stand in for it.

    ``df.attrs["filters"]`` records what was applied.
    """
    raw = _read(data_dir)
    cycles = raw["cycles"]
    n_in = len(cycles)
    mask = pd.Series(True, index=cycles.index)
    excluded = []  # type: List[str]

    if not include_test:
        test_uids = set(
            raw["cells"].loc[raw["cells"]["fold"] == C.TEST_FOLD, "cell_uid"]
        )
        drop = cycles["cell_uid"].isin(test_uids)
        mask = mask & ~drop
        excluded.append(
            "cycles of held-out test cells (fold == {0}): {1} rows".format(
                C.TEST_FOLD, int(drop.sum())
            )
        )

    if clean:
        drop = ~cycles[C.CLEAN_FLAG]
        excluded.append(
            "flagged cycles (is_clean_cycle == False): {0} rows".format(
                int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    if require_series_valid:
        from .features import series_valid_keys

        valid = series_valid_keys(data_dir, v11_dir)
        keys = pd.MultiIndex.from_arrays(
            [cycles["cell_uid"], cycles["cycle"]]
        )
        drop = pd.Series(~keys.isin(valid), index=cycles.index)
        excluded.append(
            "cycles failing is_series_valid: {0} rows".format(
                int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    out = cycles.loc[mask].copy()
    return _stamp(
        out,
        "load_cycles",
        raw,
        {
            "clean": clean,
            "include_test": include_test,
            "require_series_valid": require_series_valid,
        },
        excluded,
        n_in,
    )


# ---------------------------------------------------------------------------
# trajectories
# ---------------------------------------------------------------------------

@_docs.register
def load_trajectories(
    clean: bool = True,
    include_test: bool = False,
    labelled_only: bool = False,
    data_dir: Optional[str] = None,
):
    """Return ``(cells, cycles)`` for the cells marked ``use_for_trajectory``.

    ``use_for_trajectory`` is ``True`` for @@n_traj@@ of @@n_cells@@ cells: it excludes
    the @@n_continuation@@ continuation cells, where a test interruption injects
    1.4-5.0% of the cell's whole degradation range into a single cycle, in the wrong
    direction (decision D3). Those cells are still fine for crossing-time work, where
    the junction does not touch the label -- load them from :func:`load_cells`.

    This function's defaults protect a model: the @@n_test_cells@@ held-out test cells
    are dropped unless ``include_test=True``, leaving @@n_traj_excl_test@@ cells and
    @@n_traj_cycles_default@@ clean cycles. With ``include_test=True`` and
    ``clean=True`` it is @@n_traj@@ cells and @@n_traj_cycles@@ cycles before the clean
    filter.

    **On the number 123.** ``exploration/REPORT.md`` section 7 calls @@n_traj_labelled@@
    cells "the default trajectory training set" and
    ``exploration/comparison_external_repos.md`` section 4.2 calls @@n_traj@@ cells the
    same thing. Both numbers are right about the data and the phrase is doing double
    duty. This package uses the column, not the phrase:
    ``use_for_trajectory`` is @@n_traj@@ cells; ``use_for_trajectory & has_eol_label``
    is @@n_traj_labelled@@ cells, which is what ``labelled_only=True`` returns.

    Parameters
    ----------
    clean:
        As :func:`load_cycles`. Default ``True``.
    include_test:
        Default ``False`` -- held-out test cells are excluded. Pass ``True`` for a
        final evaluation, once.
    labelled_only:
        ``True`` also requires ``has_eol_label``, giving @@n_traj_labelled@@ cells with
        ``include_test=True`` and @@n_traj_labelled_excl_test@@ without. Default
        ``False``, because a censored cell's trajectory is valid input even though it
        carries no target (decision D4).
    data_dir:
        As :func:`load_cells`.

    Returns
    -------
    Trajectories
        A named tuple ``(cells, cycles)``; both frames carry
        ``attrs["filters"]``. Join them on ``cell_uid``.
    """
    raw = _read(data_dir)
    all_cells = raw["cells"]
    n_cells_in = len(all_cells)

    mask = all_cells["use_for_trajectory"].copy()
    excluded = [
        "cells with use_for_trajectory == False (continuations, decision D3): "
        "{0} cells".format(int((~all_cells["use_for_trajectory"]).sum()))
    ]
    if not include_test:
        drop = all_cells["fold"] == C.TEST_FOLD
        excluded.append(
            "held-out test cells (fold == {0}): {1} cells".format(
                C.TEST_FOLD, int((drop & mask).sum())
            )
        )
        mask = mask & ~drop
    if labelled_only:
        drop = ~all_cells["has_eol_label"]
        excluded.append(
            "cells with has_eol_label == False (censored): {0} cells".format(
                int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    cells = all_cells.loc[mask].copy()
    keep_uids = set(cells["cell_uid"])

    cycles_all = raw["cycles"]
    cyc_mask = cycles_all["cell_uid"].isin(keep_uids)
    cycle_excluded = list(excluded)
    if clean:
        drop = ~cycles_all[C.CLEAN_FLAG]
        cycle_excluded.append(
            "flagged cycles (is_clean_cycle == False): {0} rows".format(
                int((drop & cyc_mask).sum())
            )
        )
        cyc_mask = cyc_mask & ~drop
    cycles = cycles_all.loc[cyc_mask].copy()

    applied = {
        "clean": clean,
        "include_test": include_test,
        "labelled_only": labelled_only,
        "use_for_trajectory": True,
    }
    _stamp(cells, "load_trajectories.cells", raw, applied, excluded, n_cells_in)
    _stamp(
        cycles,
        "load_trajectories.cycles",
        raw,
        applied,
        cycle_excluded,
        len(cycles_all),
    )
    return Trajectories(cells=cells, cycles=cycles)


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------

@_docs.register
def load_labels(include_test: bool = False, data_dir: Optional[str] = None):
    """Return the cells that carry an 80%-SOH label, with their cycle life.

    @@n_labelled@@ of @@n_cells@@ cells have ``has_eol_label == True``; the other
    @@n_unlabelled@@ are censored -- they stopped above 0.88 Ah, so their trajectory is
    valid but no crossing was observed (decision D4). The @@n_test_cells@@ held-out
    cells are dropped unless ``include_test=True``, leaving @@n_labelled_excl_test@@
    rows.

    That is why this returns @@n_labelled_excl_test@@ cells where
    ``exploration/REPORT.md`` says @@n_labelled@@: the report describes the data as
    published, this applies the modelling default on top of it. Two subtractions, not
    one -- @@n_cells@@ cells, minus @@n_unlabelled@@ censored, is @@n_labelled@@ labelled;
    minus the held-out cells that carry a label leaves @@n_labelled_excl_test@@. Note
    that :func:`load_cells` returns all @@n_cells@@ by default and :func:`load_cycles`
    excludes the held-out cells, so an inner join of two default frames keeps only the
    cells both sides have: joining this frame to ``load_cells()`` drops the held-out
    cells silently rather than raising. ``df.attrs["filters"]["excluded"]`` on each
    frame names what went.

    Parameters
    ----------
    include_test:
        Default ``False``. Pass ``True`` for all @@n_labelled@@ labelled cells.
    data_dir:
        As :func:`load_cells`.

    Notes
    -----
    The target is ``eol_cycle_80pct_soh``, the cycle at which the cell crosses
    0.88 Ah = 80% of the 1.1 Ah nominal capacity (decision D0). It is also returned as
    ``cycle_life_cycles`` (an alias, int dtype) because "cycle life" is what the
    column means. ``eol_basis`` records how it was obtained per cell:

    ``strict_crossing_below_0.88Ah``
        the crossing was measured directly.
    ``test_terminated_at_criterion``
        the test stopped at the criterion, so the label is the last recorded cycle,
        within one cycle of the crossing.

    Never use the raw struct field ``cycle_life``: for 90 of @@n_cells@@ cells it is
    the record length plus one, not a measurement (``exploration/REPORT.md``
    section 5).
    """
    raw = _read(data_dir)
    all_cells = raw["cells"]
    n_in = len(all_cells)

    mask = all_cells["has_eol_label"].copy()
    excluded = [
        "cells with has_eol_label == False (censored, decision D4): {0} cells".format(
            int((~all_cells["has_eol_label"]).sum())
        )
    ]
    if not include_test:
        drop = all_cells["fold"] == C.TEST_FOLD
        excluded.append(
            "held-out test cells (fold == {0}): {1} cells".format(
                C.TEST_FOLD, int((drop & mask).sum())
            )
        )
        mask = mask & ~drop

    out = all_cells.loc[mask].copy()
    out["cycle_life_cycles"] = out["eol_cycle_80pct_soh"].astype("int64")
    return _stamp(
        out, "load_labels", raw, {"include_test": include_test}, excluded, n_in
    )


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------

def describe(data_dir: Optional[str] = None, file=None, v11_dir=None) -> Dict[str, Any]:
    """Print what each default excludes and how much is left, and return the counts.

    Everything printed is counted from the three CSVs at call time.
    """
    stream = sys.stdout if file is None else file
    raw = _read(data_dir)
    n = _compute_counts(raw)

    def say(text=""):
        print(text, file=stream)

    say("matr_clean -- the cleaned MIT-Stanford-TRI analysis set")
    say("  data tag:  {0}  (CSVs pinned to this tag, never main)".format(C.DATA_TAG))
    say("  data dir:  {0}".format(raw["data_dir"]))
    say("  found via: {0}".format(raw["source"]))
    say("  SOH basis: 80% of the {0} Ah nominal capacity = {1} Ah (decision D0)".format(
        C.NOMINAL_CAPACITY_AH, C.SOH_THRESHOLD_AH
    ))
    say()
    say("Whole analysis set")
    say("  {0:>7,} physical cells, keyed by cell_uid (== barcode)".format(n["n_cells"]))
    say("  {0:>7,} with an 80%-SOH label; {1} censored, no label".format(
        n["n_labelled"], n["n_unlabelled"]))
    say("  {0:>7,} with use_for_trajectory == True ({1} of them labelled)".format(
        n["n_traj"], n["n_traj_labelled"]))
    say("  {0:>7,} in the paper's published selection (in_paper_124)".format(
        n["n_in_paper"]))
    say("  {0:>7,} cycles, truncated at each cell's 0.88 Ah crossing".format(
        n["n_cycles"]))
    say("  {0:>7,} of those are is_clean_cycle; {1} are flagged".format(
        n["n_cycles_clean"], n["n_cycles_flagged"]))
    say()
    say("What each default excludes")
    say("  load_cells(include_test=True)       nothing -- all {0} cells. The only"
        " loader".format(n["n_cells"]))
    say("      that returns everything by default: one row per cell, no cycles.")
    say("      include_test=False drops the {0} held-out cells (fold == -1)"
        " -> {1} cells.".format(n["n_test_cells"], n["n_cells_excl_test"]))
    say("  load_cycles(clean=True,")
    say("              include_test=False)    drops {0:,} test-cell cycles and"
        " {1} flagged".format(n["n_test_cycles"], n["n_cycles_flagged_excl_test"]))
    say("      ones -> {0:,} rows. include_test=True, clean=False -> all {1:,}."
        .format(n["n_cycles_default"], n["n_cycles"]))
    say("  load_labels(include_test=False)    drops {0} censored cells and the"
        " {1} held-out".format(n["n_unlabelled"], n["n_test_cells"]))
    say("      ones -> {0} labelled cells ({1} with include_test=True).".format(
        n["n_labelled_excl_test"], n["n_labelled"]))
    say("  load_trajectories(clean=True,")
    say("                    include_test=False)")
    say("      drops {0} continuation cells (D3) and the {1} held-out ones"
        " -> {2} cells,".format(
            n["n_cells"] - n["n_traj"], n["n_test_cells"], n["n_traj_excl_test"]))
    say("      {0:,} clean cycles. labelled_only=True -> {1} cells.".format(
        n["n_traj_cycles_default"], n["n_traj_labelled_excl_test"]))
    say("  cv_splits(kind, include_test=False)")
    say("      never yields fold {0}. 'fold' -> {1} splits, 'batch' -> {2},"
        " 'policy' -> {3}".format(
            C.TEST_FOLD, n["n_folds"], n["n_batches"], n["n_policies_excl_test"]))
    say("      ({0} policies exist in the test fold only and cannot be held out)."
        .format(n["n_policies"] - n["n_policies_excl_test"]))
    say()
    say("The four flags is_clean_cycle combines (overlapping, so they do not sum)")
    say("  {0:>7,} not is_measured_cycle (2017-05-12 cycle-1 placeholders)".format(
        n["n_unmeasured"]))
    say("  {0:>7,} is_artifact_cycle   (>0.01 Ah from an 11-cycle rolling median)".format(
        n["n_artifact"]))
    say("  {0:>7,} is_restart_cycle    (chargetime spans a test interruption)".format(
        n["n_restart"]))
    say("  {0:>7,} is_junction_cycle   (within 2 cycles of a continuation seam)".format(
        n["n_junction"]))
    say()
    _describe_v11(say, data_dir, n, v11_dir)
    return n


#: Every field the three v1.0 CSVs do **not** carry, with where it now comes from.
#: Printed by :func:`describe` so the answer is never a guess.
_NOT_IN_CSVS = (
    ("IR_ohm", "v0.2.0", "internal resistance, ohm"),
    ("QCharge_Ah", "v0.2.0", "charge capacity, Ah"),
    ("Tavg_C", "v0.2.0", "mean cell temperature, degC"),
    ("Tmax_C", "v0.2.0", "max cell temperature, degC"),
    ("Tmin_C", "v0.2.0", "min cell temperature, degC"),
    ("chargetime_min", "v0.2.0", "time to 80% SOC, minutes"),
    ("t", "v0.3.0", "within-cycle elapsed time, minutes (ragged, float64)"),
    ("I", "v0.3.0", "within-cycle current, C-rate (ragged)"),
    ("V", "v0.3.0", "within-cycle voltage, V (ragged)"),
    ("T", "v0.3.0", "within-cycle temperature, degC (ragged)"),
    ("Qc", "v0.3.0", "within-cycle charge capacity, Ah (ragged)"),
    ("Qd", "v0.3.0", "within-cycle discharge capacity, Ah (ragged)"),
    ("Qdlin", "v0.3.0", "discharge capacity on the Vdlin grid, Ah (1000)"),
    ("Tdlin", "v0.3.0", "temperature on the Vdlin grid, degC (1000)"),
    ("discharge_dQdV", "v0.3.0", "dQ/dV on the Vdlin grid, Ah/V (1000)"),
    ("Vdlin", "v0.3.0", "the 1000-point 3.5 V -> 2.0 V grid itself"),
)


def _describe_v11(say, data_dir, n, v11_dir=None) -> None:
    """The v1.1 section of :func:`describe`: what arrived, and what has not."""
    from . import features

    say("The {0} fields the three v1.0 CSVs do not carry".format(len(_NOT_IN_CSVS)))
    for name, release, what in _NOT_IN_CSVS:
        say("  {0:<16} {1:<8} {2}".format(name, release, what))
    say("  Of the struct's per-cycle measurements the v1.0 CSVs carry QDischarge")
    say("  alone, as QD_Ah. The six marked v0.2.0 are in the v1.1 per-cycle index")
    say("  and are returned by load_cycle_features(); the nine series and the grid")
    say("  are HDF5-only and arrive in v0.3.0 behind the optional 'series' extra.")
    say()
    say("Not available from this loader: voltage-domain features (Qdlin, dQdV,")
    say("delta-Q). They need the three HDF5 files and arrive in v0.3.0.")
    say()

    try:
        v = features.v11_counts(data_dir, v11_dir)
    except Exception as exc:  # DataDirError, IntegrityError, DownloadError
        say("v1.1 per-cycle index: not available here")
        say("  {0}".format(str(exc).splitlines()[0]))
        say("  load_cycle_features(), load_cell_features() and")
        say("  load_cycles(require_series_valid=True) need it; everything else does")
        say("  not. Point data_dir= or ${0} at a directory holding {1}.".format(
            C.DATA_DIR_ENV, " and ".join(C.V11_REQUIRED_FILES)))
        return

    say("v1.1 per-cycle index ({0} columns; {1} read)".format(
        v["v11_index_columns"], len(C.V11_TABLE_COLUMNS)))
    say("  {0:>7,} struct cycles, of which {1:,} are the published analysis set"
        .format(v["v11_struct_cycles"], v["v11_analysis_cycles"]))
    say("  {0:>7,} past the 0.88 Ah crossing (D2 truncates these; all 2017-06-30)"
        .format(v["v11_beyond_crossing"]))
    say("  {0:>7,} zero-filled placeholders (2017-05-12 cycle 1), is_placeholder"
        .format(v["v11_placeholders"]))
    say("  {0:>7,} cycles fail is_series_valid, across {1} of {2} cells".format(
        v["v11_invalid_cycles"], v["v11_invalid_cells"], v["v11_cells"]))
    say("  {0:>7,} of those are the grid-range failures (U13), across {1} cells;"
        .format(v["v11_grid_cycles"], v["v11_grid_cells"]))
    say("          Qdlin there reaches +1,431 and -4,030 Ah on a 1.1 Ah cell.")
    say()
    say("is_clean_cycle vs is_series_valid, on the {0:,} analysis-set rows".format(
        v["v11_analysis_cycles"]))
    say("            | series-invalid | series-valid")
    say("  unclean   | {0:>14,} | {1:>12,}".format(
        v["v11_both_invalid"], v["v11_reverse"]))
    say("  clean     | {0:>14,} | {1:>12,}".format(
        v["v11_disputed"], v["v11_both_valid"]))
    say("  The {0} top-left-of-clean rows are clean in v1.0 yet fail on their own"
        .format(v["v11_disputed"]))
    say("  trace, across {0} cells; {1} run the other way. Neither flag supersedes"
        .format(v["v11_disputed_cells"], v["v11_reverse"]))
    say("  the other, and no v1.0 file or flag is edited: is_series_valid is")
    say("  carried alongside. (The 171 proposed corrections are NOT applied.)")
    say()
    say("What the v1.1 defaults exclude")
    say("  load_cycle_features(clean=True, require_series_valid=True,")
    say("                      beyond_crossing=False, include_test=False)")
    say("      -> {0:,} rows of {1:,}. All four defaults filter; pass clean=False,"
        .format(v["v11_default_rows"], v["v11_struct_cycles"]))
    say("      require_series_valid=False, beyond_crossing=True, include_test=True")
    say("      for every struct cycle with the flags intact.")
    say("      require_series_valid alone (clean=False) -> {0:,} rows.".format(
        v["v11_series_only_rows"]))
    say("  load_cell_features(include_test=False)  drops the {0} held-out cells;"
        .format(n["n_test_cells"]))
    say("      unlike load_cells(), which is the inventory view and keeps them.")
    say("  load_cycles(require_series_valid=False) unchanged from v0.1.1.")
    say("      Passing True applies the v1.1 flag to the v1.0 table.")
    say("  load_conditioning(include_test=False)  needs no v1.1 file at all,")
    say("      unless include_cycle_counts=True.")
    say()
    say("Dropped cycles leave gaps in the cycle sequence. The loader never fills,")
    say("interpolates, pads or renumbers them; df.attrs['filters'] counts each")
    say("reason. v1.1 data: {0}".format(
        "published" if C.v11_is_published() else "Zenodo record not yet published"
        " (local data_dir only)"))
