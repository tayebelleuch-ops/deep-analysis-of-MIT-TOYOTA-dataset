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
    """Filtering leaves holes in the cycle sequence. They stay holes.

    Two distinct shapes, and the loader produces both: a *truncation*, where the
    dropped cycles sit at one end (EL150800453240 loses cycles 1-53 to its splice
    run, so its kept cycles start at 54), and an *interior gap*, where a cycle is
    dropped from the middle. Neither is filled, and no label is renumbered.
    """
    out = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    everything = _all(exploration_dir, v11_dir)

    cut, interior = 0, 0
    for uid, group in out.groupby("cell_uid"):
        full = everything[(everything["cell_uid"] == uid)
                          & everything["in_analysis_set"]]
        cycles = np.sort(group["cycle"].to_numpy())
        # never duplicated, never renumbered: every label survives as itself
        assert len(np.unique(cycles)) == len(cycles), uid
        assert set(cycles).issubset(set(full["cycle"].to_numpy())), uid
        if len(group) < len(full):
            cut += 1
            if np.any(np.diff(cycles) > 1):
                interior += 1

    assert cut > 0, "no cell was filtered; the fixture is wrong"
    assert interior > 0, "no cell has an interior gap; the fixture is wrong"


def test_a_truncated_cell_keeps_its_original_labels(exploration_dir, v11_dir):
    """EL150800453240's first 53 cycles are a splice run. The default drops them
    and the survivors keep their own numbers -- they are not re-based to 1."""
    out = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    cell = out[out["cell_uid"] == "EL150800453240"]["cycle"].to_numpy()
    assert len(cell) > 0
    assert cell.min() > 1, "the corrupt early cycles were not dropped"
    assert cell.min() == 54


def test_no_imputation_of_the_series_columns(exploration_dir, v11_dir):
    """Every value is returned exactly as the file stores it -- nothing clipped,
    rounded, winsorised or filled."""
    everything = _all(exploration_dir, v11_dir)
    raw = pd.read_csv(v11_dir / C.V11_INDEX_FILE,
                      usecols=["cell_uid", "cycle"] + list(C.V11_SERIES_COLUMNS))
    merged = everything.merge(raw, on=["cell_uid", "cycle"], how="inner",
                              suffixes=("", "_raw"), validate="1:1")
    assert len(merged) == len(everything)
    for name in C.V11_SERIES_COLUMNS:
        left = merged[name].to_numpy()
        right = merged[name + "_raw"].to_numpy()
        assert np.array_equal(left, right, equal_nan=True), name


def test_summary_capacity_does_not_reveal_the_grid_failures(exploration_dir,
                                                            v11_dir):
    """Why a summary-level filter cannot catch the impossible interpolated
    values: on those cycles the capacity reading is usually unremarkable, and
    v1.0 calls most of them clean."""
    everything = _all(exploration_dir, v11_dir)
    bad = everything[~everything["series_grid_in_range"]]
    assert len(bad) > 0
    ordinary = bad["QDischarge_Ah"].between(0.8, 1.2)
    assert ordinary.any(), (
        "at least one grid-range failure must have an ordinary capacity"
    )
    assert bad["is_clean_cycle"].fillna(False).any(), (
        "at least one must be is_clean_cycle == True, or the point is moot"
    )
    # and every one of them is caught by the v1.1 flag
    assert not bad["is_series_valid"].any()


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
