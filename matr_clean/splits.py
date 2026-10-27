"""Cross-validation splits that never put one physical cell on both sides.

Three kinds, all grouped by ``barcode``: a barcode is one physical cell, including
the five cells that were cycled in 2017-05-12 and continued in 2017-06-30 as a second
struct row. Those two segments are one row of the analysis set and one group here, so
a continuation can never straddle a split.

The held-out test cells (``fold == -1``, fixed on 2026-10-27) are never yielded unless
``include_test=True``.
"""

from __future__ import annotations

from typing import Any, Iterator, List, NamedTuple, Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import _docs
from .loaders import _read

__all__ = ["Split", "cv_splits"]

KINDS = ("fold", "batch", "policy")


class Split(NamedTuple):
    """One train/test split, as arrays of ``cell_uid``.

    Attributes
    ----------
    kind:
        ``"fold"``, ``"batch"`` or ``"policy"``.
    label:
        What is held out: a fold number, a ``batch_date``, or a ``policy_canonical``.
    train:
        ``cell_uid`` values to fit on.
    test:
        ``cell_uid`` values to evaluate on.
    n_train, n_test:
        Group counts, for a quick sanity check.
    """

    kind: str
    label: Any
    train: "np.ndarray"
    test: "np.ndarray"

    @property
    def n_train(self) -> int:
        return int(len(self.train))

    @property
    def n_test(self) -> int:
        return int(len(self.test))

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "Split(kind={0!r}, label={1!r}, n_train={2}, n_test={3})".format(
            self.kind, self.label, self.n_train, self.n_test
        )


def _grouped_cells(data_dir=None) -> "pd.DataFrame":
    """One row per group, keyed on barcode, with the columns the splits need.

    Raises if a barcode ever appears with more than one fold -- that would mean a
    physical cell could straddle a split, which the fold rule forbids.
    """
    cells = _read(data_dir)["cells"]
    wanted = ["cell_uid", "barcode", "batch_date", "policy_canonical", "fold"]
    frame = cells.loc[:, wanted].copy()

    per_barcode = frame.groupby("barcode", sort=True)["fold"].nunique()
    straddling = per_barcode.loc[per_barcode > 1]
    if len(straddling) > 0:
        raise ValueError(
            "these barcodes carry more than one fold, so a physical cell would "
            "straddle a split: {0}".format(", ".join(map(str, straddling.index)))
        )
    return frame


def _uids(frame: "pd.DataFrame", mask) -> "np.ndarray":
    """cell_uid values for the selected groups, sorted for reproducibility."""
    return np.sort(frame.loc[mask, "cell_uid"].to_numpy())


@_docs.register
def cv_splits(
    kind: str = "fold",
    include_test: bool = False,
    data_dir: Optional[str] = None,
) -> Iterator[Split]:
    """Yield :class:`Split` objects of ``cell_uid`` arrays, grouped by barcode.

    Parameters
    ----------
    kind:
        ``"fold"``
            The @@n_folds@@ stored folds (``analysis_set_cells.csv:fold``, seeded
            20261027, stratified on ``batch_date`` and ``has_eol_label``). Each fold
            is held out in turn: @@n_folds@@ splits.

            **This split only tests new cells from batches and policies the model has
            already seen.** Every fold contains cells from all @@n_batches@@ batches,
            and a policy is usually spread across folds, so a good score here says
            nothing about generalising to a new batch or a new charging policy. Use
            ``"batch"`` and ``"policy"`` for those two questions.
        ``"batch"``
            Leave one batch out: @@n_batches@@ splits, one per ``batch_date``. The
            batches differ in CV cutoff current, rest scheme, end-of-life criterion and
            baseline temperature (``exploration/REPORT.md`` section 8), so this is the
            honest test of cross-batch transfer.
        ``"policy"``
            Leave one charging policy out, on ``policy_canonical``. With the default
            ``include_test=False`` that is @@n_policies_excl_test@@ splits: of the
            @@n_policies@@ policies in the data, the rest appear only among the
            held-out test cells and so cannot be held out again.
    include_test:
        Default ``False``: the @@n_test_cells@@ cells with ``fold == -1`` appear in no
        train and no test set. With ``True`` they take part, and ``kind="fold"``
        yields one extra, final split labelled ``-1`` whose test set is exactly those
        cells and whose train set is folds 0-@@last_fold@@.
    data_dir:
        As :func:`matr_clean.load_cells`.

    Yields
    ------
    Split
        ``(kind, label, train, test)``, where ``train`` and ``test`` are sorted arrays
        of ``cell_uid``. Filter a cycle table with
        ``cycles[cycles.cell_uid.isin(split.train)]``.

    Notes
    -----
    Cells are never addressed by row position. ``cell_uid`` equals ``barcode`` in this
    dataset, and grouping is done on ``barcode`` so that the two segments of a
    continued cell stay together.
    """
    if kind not in KINDS:
        raise ValueError(
            "kind must be one of {0}, not {1!r}".format(", ".join(KINDS), kind)
        )

    frame = _grouped_cells(data_dir)
    is_test = frame["fold"] == C.TEST_FOLD
    pool = frame if include_test else frame.loc[~is_test]

    if kind == "fold":
        folds = sorted(int(f) for f in pool["fold"].unique() if int(f) != C.TEST_FOLD)
        for fold in folds:
            held = pool["fold"] == fold
            yield Split(
                kind="fold",
                label=fold,
                train=_uids(pool, ~held & (pool["fold"] != C.TEST_FOLD)),
                test=_uids(pool, held),
            )
        if include_test:
            held = frame["fold"] == C.TEST_FOLD
            yield Split(
                kind="fold",
                label=C.TEST_FOLD,
                train=_uids(frame, ~held),
                test=_uids(frame, held),
            )
        return

    column = "batch_date" if kind == "batch" else "policy_canonical"
    labels = sorted(pool[column].dropna().unique())
    for label in labels:
        held = pool[column] == label
        train = _uids(pool, ~held)
        test = _uids(pool, held)
        if len(train) == 0 or len(test) == 0:
            continue
        yield Split(kind=kind, label=label, train=train, test=test)


def split_labels(kind: str = "fold", include_test: bool = False, data_dir=None) -> List[Any]:
    """Return just the held-out labels :func:`cv_splits` would yield, in order."""
    return [s.label for s in cv_splits(kind, include_test=include_test, data_dir=data_dir)]
