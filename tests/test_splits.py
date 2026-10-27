"""cv_splits: grouping, coverage, and that the held-out fold stays held out."""

from __future__ import annotations

import pytest

import matr_clean as mc
from matr_clean import constants as C


def test_fold_split_yields_five_splits(exploration_dir):
    splits = list(mc.cv_splits("fold", data_dir=exploration_dir))
    assert len(splits) == 5
    assert [s.label for s in splits] == [0, 1, 2, 3, 4]


def test_no_cell_uid_or_barcode_appears_in_two_folds(exploration_dir, cells):
    """Every cell is tested exactly once across the five folds, and never while
    it is also being trained on."""
    splits = list(mc.cv_splits("fold", data_dir=exploration_dir))
    seen = []
    for split in splits:
        assert set(split.train).isdisjoint(set(split.test))
        seen.extend(split.test.tolist())
    assert len(seen) == len(set(seen)), "a cell is held out by two folds"

    non_test = cells.loc[cells["fold"] != C.TEST_FOLD, "cell_uid"]
    assert set(seen) == set(non_test)

    # and the same holds for barcode, the grouping key
    uid_to_barcode = dict(zip(cells["cell_uid"], cells["barcode"]))
    barcodes = [uid_to_barcode[u] for u in seen]
    assert len(barcodes) == len(set(barcodes))


def test_continuation_cells_are_one_group_in_one_fold(exploration_dir, cells):
    """The five cells that span 2017-05-12 and 2017-06-30 are one row, one barcode
    and therefore one fold -- the two segments can never straddle a split."""
    continued = cells.loc[cells["is_continuation"]]
    assert len(continued) == 5
    # each carries two segments in all_segments, and exactly one fold value
    for _, row in continued.iterrows():
        assert len(str(row["all_segments"]).split("|")) == 2
    assert continued.groupby("barcode")["fold"].nunique().max() == 1

    for split in mc.cv_splits("fold", include_test=True, data_dir=exploration_dir):
        for uid in continued["cell_uid"]:
            on_both = (uid in set(split.train)) and (uid in set(split.test))
            assert not on_both


def test_every_barcode_has_exactly_one_fold(cells):
    assert cells.groupby("barcode")["fold"].nunique().max() == 1


def test_test_fold_never_appears_by_default(exploration_dir, cells):
    held_out = set(cells.loc[cells["fold"] == C.TEST_FOLD, "cell_uid"])
    assert len(held_out) == 27
    for kind in ("fold", "batch", "policy"):
        for split in mc.cv_splits(kind, data_dir=exploration_dir):
            assert split.label != C.TEST_FOLD
            assert not held_out & set(split.train)
            assert not held_out & set(split.test)


def test_include_test_adds_a_final_fold_split(exploration_dir, cells):
    splits = list(mc.cv_splits("fold", include_test=True, data_dir=exploration_dir))
    assert [s.label for s in splits] == [0, 1, 2, 3, 4, C.TEST_FOLD]
    last = splits[-1]
    held_out = set(cells.loc[cells["fold"] == C.TEST_FOLD, "cell_uid"])
    assert set(last.test) == held_out
    assert set(last.train) == set(cells["cell_uid"]) - held_out


def test_leave_one_batch_out_covers_each_batch_exactly_once(exploration_dir, cells):
    splits = list(mc.cv_splits("batch", data_dir=exploration_dir))
    batches = sorted(cells["batch_date"].unique())
    assert len(splits) == len(batches) == 3
    assert [s.label for s in splits] == batches

    non_test = cells.loc[cells["fold"] != C.TEST_FOLD]
    for split in splits:
        expected = set(non_test.loc[non_test["batch_date"] == split.label, "cell_uid"])
        assert set(split.test) == expected
        assert set(split.train) == set(non_test["cell_uid"]) - expected
        assert set(split.train).isdisjoint(set(split.test))

    # every cell is held out exactly once, so the three test sets partition the pool
    held = [u for s in splits for u in s.test]
    assert len(held) == len(set(held)) == len(non_test)


def test_leave_one_policy_out(exploration_dir, cells):
    splits = list(mc.cv_splits("policy", data_dir=exploration_dir))
    non_test = cells.loc[cells["fold"] != C.TEST_FOLD]
    expected_labels = sorted(non_test["policy_canonical"].unique())
    assert [s.label for s in splits] == expected_labels
    assert len(splits) == 60

    for split in splits:
        expected = set(
            non_test.loc[non_test["policy_canonical"] == split.label, "cell_uid"]
        )
        assert set(split.test) == expected
        assert set(split.train).isdisjoint(expected)
        # no policy leaks across the split
        train_policies = set(
            non_test.loc[non_test["cell_uid"].isin(split.train), "policy_canonical"]
        )
        assert split.label not in train_policies


def test_policy_split_with_test_cells_covers_all_policies(exploration_dir, cells):
    splits = list(mc.cv_splits("policy", include_test=True, data_dir=exploration_dir))
    assert len(splits) == cells["policy_canonical"].nunique() == 69


def test_splits_return_cell_uids_not_positions(exploration_dir, cells):
    split = next(iter(mc.cv_splits("fold", data_dir=exploration_dir)))
    assert set(split.train) <= set(cells["cell_uid"])
    assert all(isinstance(u, str) for u in split.test)


def test_bad_kind_raises(exploration_dir):
    with pytest.raises(ValueError, match="kind must be one of"):
        list(mc.cv_splits("random", data_dir=exploration_dir))


def test_split_labels_helper(exploration_dir):
    assert mc.split_labels("batch", data_dir=exploration_dir) == [
        "2017-05-12",
        "2017-06-30",
        "2018-04-12",
    ]
