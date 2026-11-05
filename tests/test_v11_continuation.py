"""Addressing: by channel and barcode, never by position; by source_batch_date.

The two traps this dataset sets, and the two a loader can regress into silently:

1. **No struct stores its rows in channel order.** ``source_struct_index`` differs
   from ``source_channel - 1`` for 113 of the 140 real struct rows, so a cell
   addressed by position is, usually, a different cell.
2. **Five cells are continued across batches**, and ``batch_date`` in both v1.0
   CSVs is the *first* segment's on every row. A segment-2 cycle of
   ``EL150800460514`` says ``2017-05-12`` while its series live in
   ``within_cycle_2017-06-30.h5``. Dispatching on ``batch_date`` opens the wrong
   file and finds nothing.

Both are asserted against the fixture, which carries real rows for both.
"""

from __future__ import annotations

import pytest

import matr_clean as mc
from matr_clean import constants as C


def _all(exploration_dir, v11_dir):
    return mc.load_cycle_features(
        clean=False, require_series_valid=False, beyond_crossing=True,
        include_test=True, data_dir=exploration_dir, v11_dir=v11_dir,
    )


# ---------------------------------------------------------------------------
# trap 1: position is not the channel
# ---------------------------------------------------------------------------

def test_struct_position_is_not_the_channel(exploration_dir, v11_dir):
    out = _all(exploration_dir, v11_dir)
    mismatched = out["source_struct_index"] != out["source_channel"] - 1
    assert mismatched.any(), (
        "the fixture must contain cells whose struct row is not their channel; "
        "this holds for 113 of the 140 real struct rows"
    )


def test_each_cell_segment_resolved_to_exactly_one_struct_row(exploration_dir,
                                                              v11_dir):
    """Provenance is per (cell, segment) and never varies cycle to cycle."""
    out = _all(exploration_dir, v11_dir)
    for uid, group in out.groupby("cell_uid"):
        for segment, rows in group.groupby("segment"):
            assert rows["source_struct_index"].nunique() == 1, (uid, segment)
            assert rows["source_channel"].nunique() == 1, (uid, segment)
            assert rows["source_batch_date"].nunique() == 1, (uid, segment)


def test_a_positional_lookup_would_pick_a_different_row(exploration_dir, v11_dir):
    """The negative control. Had the loader indexed by ``channel - 1``, it would
    have read another cell's data; this asserts the two genuinely differ."""
    out = _all(exploration_dir, v11_dir)
    pairs = out.drop_duplicates(["cell_uid", "segment"])[
        ["cell_uid", "segment", "source_channel", "source_struct_index",
         "source_batch_date"]
    ]
    wrong = pairs[pairs["source_struct_index"] != pairs["source_channel"] - 1]
    assert len(wrong) > 0, "fixture must contain a non-positional cell"
    for row in wrong.itertuples():
        assert row.source_struct_index != row.source_channel - 1
    # and in at least one file, the row that position would have claimed is
    # occupied by a different channel entirely
    collisions = 0
    for date, rows in pairs.groupby("source_batch_date"):
        occupied = dict(zip(rows["source_struct_index"], rows["source_channel"]))
        for row in rows.itertuples():
            guess = row.source_channel - 1
            if guess in occupied and occupied[guess] != row.source_channel:
                collisions += 1
    assert collisions > 0, (
        "no positional guess lands on another channel's row in this fixture"
    )


def test_cells_are_keyed_by_barcode_not_by_channel(exploration_dir, v11_dir):
    """``cell_uid`` is the upper-cased barcode, and it is what joins."""
    out = _all(exploration_dir, v11_dir)
    assert (out["cell_uid"] == out["cell_uid"].str.upper()).all()
    # a channel number is not unique across batches, so it cannot be the key
    per_channel = out.groupby("source_channel")["cell_uid"].nunique()
    assert (per_channel > 1).any(), "channel numbers repeat across batches"


# ---------------------------------------------------------------------------
# trap 2: source_batch_date, not batch_date
# ---------------------------------------------------------------------------

def test_the_continuation_cells_span_two_files(exploration_dir, v11_dir):
    out = _all(exploration_dir, v11_dir)
    spans = out.groupby("cell_uid")["source_batch_date"].nunique()
    two_file = sorted(spans[spans > 1].index)
    assert two_file, "the fixture must contain a continuation cell"
    for uid in two_file:
        assert uid in C.V11_CONTINUATION_CELLS


def test_all_five_continuation_cells_are_named_in_the_constants():
    assert len(C.V11_CONTINUATION_CELLS) == 5
    assert len(set(C.V11_CONTINUATION_CELLS)) == 5


def test_segment_two_rows_name_a_file_batch_date_does_not(exploration_dir,
                                                          v11_dir):
    """The trap, stated as a test."""
    out = _all(exploration_dir, v11_dir)
    cells = mc.load_cells(data_dir=exploration_dir)
    batch_of = dict(zip(cells["cell_uid"], cells["batch_date"]))

    checked = 0
    for uid, group in out.groupby("cell_uid"):
        if group["segment"].nunique() < 2:
            continue
        second = group[group["segment"] == 2]
        assert len(second) > 0
        assert (second["source_batch_date"] != batch_of[uid]).all()
        assert (second["source_batch_date"] == "2017-06-30").all()
        assert batch_of[uid] == "2017-05-12"
        # segment 1 agrees with batch_date, which is exactly why it misleads
        first = group[group["segment"] == 1]
        if len(first):
            assert (first["source_batch_date"] == batch_of[uid]).all()
        checked += 1
    assert checked > 0, "no two-segment cell in the fixture"


def test_dispatching_on_batch_date_would_find_nothing(exploration_dir, v11_dir):
    """A loader that grouped by ``batch_date`` would look for segment-2 cycles in
    the 2017-05-12 file, which does not contain them."""
    out = _all(exploration_dir, v11_dir)
    cells = mc.load_cells(data_dir=exploration_dir)
    batch_of = dict(zip(cells["cell_uid"], cells["batch_date"]))

    for uid, group in out.groupby("cell_uid"):
        second = group[group["segment"] == 2]
        if second.empty:
            continue
        wrong_file = batch_of[uid]
        right_file = second["source_batch_date"].iloc[0]
        assert wrong_file != right_file
        # the cycles of segment 2 appear under no other cell in the wrong file
        in_wrong = out[(out["source_batch_date"] == wrong_file)
                       & (out["cell_uid"] == uid)]
        assert set(second["cycle"]).isdisjoint(set(in_wrong["cycle"]))


def test_segment_cycle_ranges_are_one_continuous_numbering(exploration_dir,
                                                           v11_dir):
    """Segments are concatenated: segment 2 continues segment 1's count."""
    out = _all(exploration_dir, v11_dir)
    for uid, group in out.groupby("cell_uid"):
        if group["segment"].nunique() < 2:
            continue
        first = group[group["segment"] == 1]["cycle"]
        second = group[group["segment"] == 2]["cycle"]
        if len(first) and len(second):
            assert first.max() < second.min()


def test_h5_row_restarts_in_each_file(exploration_dir, v11_dir):
    """``h5_row`` indexes within its own file, so it is only meaningful together
    with ``source_batch_date``."""
    out = _all(exploration_dir, v11_dir)
    for uid, group in out.groupby("cell_uid"):
        for date, rows in group.groupby("source_batch_date"):
            ordered = rows.sort_values("cycle")["h5_row"].to_numpy()
            assert (ordered[1:] > ordered[:-1]).all(), (uid, date)


def test_cycles_ten_and_one_hundred_are_always_in_segment_one(exploration_dir,
                                                              v11_dir):
    """Why the paper's cycle-10/100 feature is unaffected by continuation."""
    out = _all(exploration_dir, v11_dir)
    early = out[out["cycle"].isin((10, 100))]
    assert len(early) > 0
    assert (early["segment"] == 1).all()


def test_the_dispatch_constant_is_keyed_by_source_batch_date(exploration_dir,
                                                             v11_dir):
    out = _all(exploration_dir, v11_dir)
    for date in out["source_batch_date"].unique():
        assert date in C.V11_H5_FILES, date
    assert set(C.V11_H5_FILES) == {"2017-05-12", "2017-06-30", "2018-04-12"}


def test_batch_date_is_absent_so_it_cannot_be_used_by_mistake(exploration_dir,
                                                              v11_dir):
    out = _all(exploration_dir, v11_dir)
    assert "batch_date" not in out.columns
    assert "source_batch_date" in out.columns
