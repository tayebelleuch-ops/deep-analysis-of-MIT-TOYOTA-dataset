"""What each v0.2.0 default excludes, and that nothing is masked or filled."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import matr_clean as mc
from matr_clean import constants as C


def _all(exploration_dir, v11_dir):
    return mc.load_cycle_features(
        clean=False, require_series_valid=False, beyond_crossing=True,
        include_test=True, data_dir=exploration_dir, v11_dir=v11_dir,
    )


def test_every_default_filters(exploration_dir, v11_dir):
    everything = _all(exploration_dir, v11_dir)
    default = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert len(default) < len(everything)
    assert default["in_analysis_set"].all()
    assert default[C.V11_SERIES_FLAG].all()
    assert (default["is_clean_cycle"].fillna(True)).all()
    assert not default["is_placeholder"].any()


def test_placeholders_are_dropped_by_the_series_filter_not_zeroed(
    exploration_dir, v11_dir
):
    """The nan_to_num pitfall, at table level: a placeholder is never a zero row."""
    everything = _all(exploration_dir, v11_dir)
    placeholders = everything[everything["is_placeholder"]]
    assert len(placeholders) > 0
    # they fail series_present, hence is_series_valid, hence the default drops them
    assert not placeholders[C.V11_SERIES_FLAG].any()
    assert not placeholders["series_present"].any()
    assert (placeholders["n_samples"] == 2).all()
    assert (placeholders["grid_len_raw"] == 2).all()

    default = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert not default["is_placeholder"].any()

    # and with the filters off they are still *flagged*, not silently zeroed away:
    # the row survives, carrying zeros, so a caller who ignores the flag can see
    # exactly what they are getting.
    assert (placeholders["QDischarge_Ah"] == 0).all()


def test_require_series_valid_is_not_redundant_with_clean(exploration_dir, v11_dir):
    """171 rows nationally; on the fixture, simply: both directions exist."""
    everything = _all(exploration_dir, v11_dir)
    in_set = everything["in_analysis_set"]
    clean = everything["is_clean_cycle"].fillna(False)
    valid = everything[C.V11_SERIES_FLAG]
    disputed = int((in_set & clean & ~valid).sum())
    reverse = int((in_set & ~clean & valid).sum())
    assert disputed > 0, "fixture must contain clean-but-series-invalid rows"
    assert reverse > 0, "fixture must contain series-valid-but-unclean rows"

    only_clean = mc.load_cycle_features(
        require_series_valid=False, data_dir=exploration_dir, v11_dir=v11_dir)
    only_series = mc.load_cycle_features(
        clean=False, data_dir=exploration_dir, v11_dir=v11_dir)
    both = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert len(both) < len(only_clean)
    assert len(both) < len(only_series)
    # neither flag is a subset of the other
    assert len(only_clean) != len(only_series)


def test_beyond_crossing_rows_carry_na_for_the_v1_0_flags(exploration_dir, v11_dir):
    everything = _all(exploration_dir, v11_dir)
    beyond = everything[everything["beyond_crossing"]]
    assert len(beyond) > 0
    assert beyond["is_clean_cycle"].isna().all()
    assert beyond["soh"].isna().all()
    # but the v1.1 flags are real on every row, which is why they can be filtered
    assert beyond[C.V11_SERIES_FLAG].notna().all()


def test_clean_keeps_rows_v1_0_never_judged(exploration_dir, v11_dir):
    """clean=True drops `is False`, not `is not True`: <NA> is not a judgement."""
    out = mc.load_cycle_features(
        clean=True, require_series_valid=False, beyond_crossing=True,
        include_test=True, data_dir=exploration_dir, v11_dir=v11_dir)
    assert out["beyond_crossing"].sum() > 0
    assert out.loc[out["beyond_crossing"], "is_clean_cycle"].isna().all()


def test_beyond_crossing_default_excludes_them(exploration_dir, v11_dir):
    out = mc.load_cycle_features(
        clean=False, require_series_valid=False, include_test=True,
        data_dir=exploration_dir, v11_dir=v11_dir)
    assert not out["beyond_crossing"].any()
    assert out["in_analysis_set"].all()


def test_filters_attr_counts_every_reason(exploration_dir, v11_dir):
    out = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    filters = out.attrs["filters"]
    assert filters["function"] == "load_cycle_features"
    assert filters["n_rows_out"] == len(out)
    assert filters["n_rows_in"] > filters["n_rows_out"]
    assert filters["applied"]["require_series_valid"] is True
    assert filters["applied"]["clean"] is True
    assert filters["v11_published"] is False
    reasons = " ".join(filters["excluded"])
    for fragment in ("beyond_crossing", "held-out test cells",
                     "is_clean_cycle", "is_series_valid"):
        assert fragment in reasons
    assert len(filters["excluded"]) == 4


def test_nothing_is_filled_and_gaps_are_left(exploration_dir, v11_dir):
    """Filtering leaves holes in the cycle sequence. They stay holes."""
    out = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    everything = _all(exploration_dir, v11_dir)
    # pick a cell the filters actually cut into
    cut = None
    for uid, group in out.groupby("cell_uid"):
        full = everything[(everything["cell_uid"] == uid)
                          & everything["in_analysis_set"]]
        if len(group) < len(full):
            cut = (uid, group, full)
            break
    assert cut is not None, "no cell was filtered; fixture is wrong"
    uid, group, full = cut
    cycles = group["cycle"].to_numpy()
    assert len(np.unique(cycles)) == len(cycles)
    # a gap exists, and the cycle labels were not renumbered to hide it
    assert np.any(np.diff(np.sort(cycles)) > 1)
    assert set(cycles).issubset(set(full["cycle"].to_numpy()))


def test_no_imputation_of_the_series_columns(exploration_dir, v11_dir):
    """Out-of-band values are returned as stored, not clipped or repaired."""
    everything = _all(exploration_dir, v11_dir)
    bad = everything[~everything["series_grid_in_range"]]
    assert len(bad) > 0
    # the summary columns on those rows are ordinary -- which is exactly why a
    # summary-level filter cannot catch them
    assert bad["QDischarge_Ah"].between(0.0, 1.2).all()


def test_include_test_governs_the_held_out_cells(exploration_dir, v11_dir):
    cells = mc.load_cells(data_dir=exploration_dir)
    test_uids = set(cells.loc[cells["fold"] == C.TEST_FOLD, "cell_uid"])
    default = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert not default["cell_uid"].isin(test_uids).any()


def test_row_order_is_the_index_files_own(exploration_dir, v11_dir):
    """Never re-sorted: the file's order is ascending channel, then cycle."""
    out = _all(exploration_dir, v11_dir)
    raw = pd.read_csv(v11_dir / C.V11_INDEX_FILE,
                      usecols=["cell_uid", "cycle"])
    assert list(out["cell_uid"]) == list(raw["cell_uid"])
    assert list(out["cycle"]) == list(raw["cycle"])
