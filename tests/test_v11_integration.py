"""Integration: every published v1.1 count, against the real 114,738-row index.

Skipped unless ``MATR_CLEAN_TEST_DATA`` points at a directory holding the real
``within_cycle_index.csv`` and ``within_cycle_cells.csv``::

    MATR_CLEAN_TEST_DATA=/path/to/extract_out .venv/bin/python -m pytest tests/

The fixture suite is what CI runs; this is what proves the fixture's numbers are
the real numbers. Every value asserted here is quoted in ``REPORT_v1.1.md`` or
``MANIFEST_v1.1.md``, and every one is also a named constant in
``matr_clean.constants``, so a drift in either direction fails.

The real files are opened read-only and never written. The last test checks that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import matr_clean as mc
from matr_clean import constants as C


@pytest.fixture(scope="module")
def real(real_v11_dir, exploration_dir):
    """Every struct cycle, every flag intact."""
    return mc.load_cycle_features(
        clean=False, require_series_valid=False, beyond_crossing=True,
        include_test=True, data_dir=exploration_dir, v11_dir=real_v11_dir,
    )


# ---------------------------------------------------------------------------
# row counts
# ---------------------------------------------------------------------------

def test_every_struct_cycle_is_present(real):
    assert len(real) == C.V11_STRUCT_CYCLES == 114738


def test_the_analysis_set_reconciles(real, exploration_dir):
    assert int(real["in_analysis_set"].sum()) == C.V11_ANALYSIS_CYCLES == 113559
    published = mc.load_cycles(
        clean=False, include_test=True, data_dir=exploration_dir
    )
    assert int(real["in_analysis_set"].sum()) == len(published)
    # 114,738 - 1,179 = 113,559, exactly
    assert (C.V11_STRUCT_CYCLES - C.V11_BEYOND_CROSSING) == C.V11_ANALYSIS_CYCLES


def test_beyond_crossing_and_placeholders(real):
    assert int(real["beyond_crossing"].sum()) == C.V11_BEYOND_CROSSING == 1179
    assert int(real["is_placeholder"].sum()) == C.V11_PLACEHOLDERS == 46
    # all the truncated cycles are 2017-06-30; all the placeholders 2017-05-12
    assert set(real.loc[real["beyond_crossing"], "source_batch_date"]) == {
        "2017-06-30"
    }
    assert set(real.loc[real["is_placeholder"], "source_batch_date"]) == {
        "2017-05-12"
    }
    # one placeholder per 2017-05-12 cell, always at cycle 1
    assert set(real.loc[real["is_placeholder"], "cycle"]) == {1}


def test_cells_and_struct_rows(real):
    assert real["cell_uid"].nunique() == C.V11_CELLS == 135
    rows = real.drop_duplicates(["cell_uid", "segment"])
    assert len(rows) == C.V11_STRUCT_ROWS == 140


def test_the_key_is_unique_over_all_114738_rows(real):
    assert not real.duplicated(["cell_uid", "cycle"]).any()


# ---------------------------------------------------------------------------
# the join proof
# ---------------------------------------------------------------------------

def test_qdischarge_matches_the_v1_0_table_bit_for_bit(real, exploration_dir):
    """Equal row counts would pass under a misaligned numbering; equal capacity
    values bit-for-bit would not. This is the join proof."""
    published = mc.load_cycles(
        clean=False, include_test=True, data_dir=exploration_dir
    )
    merged = real.merge(
        published[["cell_uid", "cycle", "QD_Ah"]],
        on=["cell_uid", "cycle"], how="inner", validate="1:1",
    )
    assert len(merged) == C.V11_ANALYSIS_CYCLES
    assert np.array_equal(
        merged["QDischarge_Ah"].to_numpy(), merged["QD_Ah"].to_numpy()
    )


# ---------------------------------------------------------------------------
# the validity flags
# ---------------------------------------------------------------------------

def test_is_series_valid_totals(real):
    """249 across 97 cells -- the total, not the 48/32/34 of one component."""
    invalid = ~real["is_series_valid"]
    assert int(invalid.sum()) == C.V11_SERIES_INVALID_CYCLES == 249
    assert real.loc[invalid, "cell_uid"].nunique() == C.V11_SERIES_INVALID_CELLS == 97


def test_the_grid_range_component_is_48_32_34(real):
    """The impossible interpolated values, U13. This is the triple that the
    earlier draft spec mistook for the is_series_valid total."""
    bad = ~real["series_grid_in_range"]
    assert int(bad.sum()) == C.V11_GRID_RANGE_CYCLES == 48
    assert real.loc[bad, "cell_uid"].nunique() == C.V11_GRID_RANGE_CELLS == 32
    clean = real["is_clean_cycle"].fillna(False)
    assert int((bad & clean).sum()) == C.V11_GRID_RANGE_CLEAN_IN_V1_0 == 34
    # and it is a strict subset of is_series_valid's failures
    assert int(bad.sum()) < C.V11_SERIES_INVALID_CYCLES
    assert (~real.loc[bad, "is_series_valid"]).all()


def test_the_two_by_two_against_is_clean_cycle(real):
    in_set = real["in_analysis_set"]
    clean = real["is_clean_cycle"].fillna(False)
    valid = real["is_series_valid"]
    assert int((in_set & clean & ~valid).sum()) == C.V11_DISPUTED_CYCLES == 171
    assert int((in_set & ~clean & valid).sum()) == C.V11_REVERSE_CYCLES == 87
    assert int((in_set & ~clean & ~valid).sum()) == C.V11_BOTH_INVALID_CYCLES == 78
    assert int((in_set & clean & valid).sum()) == C.V11_BOTH_VALID_CYCLES == 113223
    # the four cells partition the analysis set
    assert (C.V11_DISPUTED_CYCLES + C.V11_REVERSE_CYCLES
            + C.V11_BOTH_INVALID_CYCLES + C.V11_BOTH_VALID_CYCLES
            ) == C.V11_ANALYSIS_CYCLES


def test_the_disputed_set_spans_54_cells(real):
    in_set = real["in_analysis_set"]
    clean = real["is_clean_cycle"].fillna(False)
    disputed = in_set & clean & ~real["is_series_valid"]
    assert real.loc[disputed, "cell_uid"].nunique() == C.V11_DISPUTED_CELLS == 54


def test_placeholders_fail_series_present_and_nothing_else_explains_them(real):
    placeholders = real[real["is_placeholder"]]
    assert len(placeholders) == 46
    assert not placeholders["series_present"].any()
    assert not placeholders["is_series_valid"].any()
    assert (placeholders["n_samples"] == 2).all()
    assert (placeholders["grid_len_raw"] == 2).all()
    # v1.0 agrees: is_placeholder is exactly ~is_measured_cycle
    assert not placeholders["is_measured_cycle"].fillna(False).any()
    measured = real["is_measured_cycle"].fillna(True)
    assert int((~measured).sum()) == 46


def test_two_components_never_fire(real):
    """series_time_monotone and series_no_nan fail on zero cycles: there is no NaN
    anywhere in the nine series, and the worst backward time step is float64
    rounding."""
    assert int((~real["series_time_monotone"]).sum()) == 0
    assert int((~real["series_no_nan"]).sum()) == 0


def test_component_failure_counts(real):
    """Each component's count, as EXTRACTION.md section 5 tabulates them."""
    expected = {
        "series_present": 46,
        "series_time_monotone": 0,
        "series_time_contiguous": 135,
        "series_duration_plausible": 131,
        "series_length_plausible": 53,
        "series_voltage_in_range": 15,
        "series_current_in_range": 3,
        "series_grid_in_range": 48,
        "series_no_nan": 0,
    }
    actual = {name: int((~real[name]).sum()) for name in C.V11_COMPONENT_FLAGS}
    assert actual == expected
    # they overlap, so they do not sum to 249
    assert sum(expected.values()) != C.V11_SERIES_INVALID_CYCLES


def test_the_impossible_qdlin_extremes_are_present_and_unrepaired(real,
                                                                  real_v11_dir):
    """+1,430.7 Ah and -4,030.3 Ah on a 1.1 Ah cell, returned as stored."""
    diagnostics = pd.read_csv(
        real_v11_dir / C.V11_INDEX_FILE,
        usecols=["cell_uid", "cycle", "Qdlin_min", "Qdlin_max",
                 "series_grid_in_range"],
    )
    assert round(float(diagnostics["Qdlin_max"].max()), 1) == 1430.7
    assert round(float(diagnostics["Qdlin_min"].min()), 1) == -4030.3
    worst_hi = diagnostics.loc[diagnostics["Qdlin_max"].idxmax()]
    worst_lo = diagnostics.loc[diagnostics["Qdlin_min"].idxmin()]
    assert worst_hi["cell_uid"] == "EL150800460511" and worst_hi["cycle"] == 247
    assert worst_lo["cell_uid"] == "EL150800737364" and worst_lo["cycle"] == 368
    assert not bool(worst_hi["series_grid_in_range"])
    assert not bool(worst_lo["series_grid_in_range"])


def test_the_two_worst_cells_carry_102_of_the_249(real):
    """EL150800453240 (the splice run) and EL150800737364 (the over-sampling
    fault) between them hold most of the damage."""
    invalid = real[~real["is_series_valid"]]
    counts = invalid["cell_uid"].value_counts()
    assert counts.loc["EL150800453240"] == 53
    assert counts.loc["EL150800737364"] == 49
    assert counts.loc["EL150800453240"] + counts.loc["EL150800737364"] == 102


# ---------------------------------------------------------------------------
# continuation, on the real five
# ---------------------------------------------------------------------------

def test_exactly_five_cells_span_two_files(real):
    spans = real.groupby("cell_uid")["source_batch_date"].nunique()
    two_file = sorted(spans[spans > 1].index)
    assert two_file == sorted(C.V11_CONTINUATION_CELLS)
    assert len(two_file) == 5


def test_the_real_segment_boundaries(real):
    """The published offsets, which the draft spec quoted as 'around 1176-1226'."""
    expected = {
        "EL150800460486": (1178, 1179, 2159),
        "EL150800460514": (1189, 1190, 1851),
        "EL150800460623": (1176, 1177, 2236),
        "EL150800464865": (1226, 1227, 1708),
        "EL150800464977": (1225, 1226, 1433),
    }
    for uid, (last_first, first_second, last_second) in expected.items():
        cell = real[real["cell_uid"] == uid]
        seg1 = cell[cell["segment"] == 1]
        seg2 = cell[cell["segment"] == 2]
        assert int(seg1["cycle"].max()) == last_first, uid
        assert int(seg2["cycle"].min()) == first_second, uid
        assert int(seg2["cycle"].max()) == last_second, uid
        assert set(seg1["source_batch_date"]) == {"2017-05-12"}, uid
        assert set(seg2["source_batch_date"]) == {"2017-06-30"}, uid


def test_struct_position_differs_from_channel_for_113_of_140_rows(real):
    rows = real.drop_duplicates(["cell_uid", "segment"])
    mismatched = rows["source_struct_index"] != rows["source_channel"] - 1
    assert int(mismatched.sum()) == 113
    assert len(rows) == 140


def test_every_cell_has_at_least_170_cycles_in_segment_one(real):
    """Why a 25-cycle early window never crosses a file."""
    seg1 = real[real["segment"] == 1]
    per_cell = seg1.groupby("cell_uid")["cycle"].count()
    assert per_cell.min() == 170
    assert (per_cell >= 25).all()
    assert seg1.groupby("cell_uid")["cycle"].min().eq(1).all()


# ---------------------------------------------------------------------------
# the early window the colleagues' model consumes
# ---------------------------------------------------------------------------

def test_the_first_25_labels_carry_93_invalid_positions(real):
    """What a 25-cycle autoencoder window actually contains. This is the number
    that matters to anyone calling np.nan_to_num on it."""
    window = real[(real["segment"] == 1) & (real["cycle"] <= 25)]
    assert len(window) == 135 * 25
    invalid = window[~window["is_series_valid"]]
    assert len(invalid) == 93
    assert invalid["cell_uid"].nunique() == 48
    assert int(invalid["is_placeholder"].sum()) == 46
    # one whole cell is unusable across the entire window
    assert int((invalid["cell_uid"] == "EL150800453240").sum()) == 25
    # and six positions hold physically impossible interpolated values
    assert int((~window["series_grid_in_range"]).sum()) == 6


def test_the_measured_window_shifts_only_the_2017_05_12_cells(real):
    """window="measured" (the opt-in convention) is labels 2..26 for exactly the 46
    cells with a placeholder, and labels 1..25 for the other 89."""
    seg1 = real[real["segment"] == 1].sort_values(["cell_uid", "cycle"])
    shifted, unshifted = 0, 0
    for uid, group in seg1.groupby("cell_uid"):
        measured = group[~group["is_placeholder"]].head(25)
        if int(measured["cycle"].min()) == 2:
            shifted += 1
            assert int(measured["cycle"].max()) == 26
        else:
            unshifted += 1
            assert int(measured["cycle"].min()) == 1
            assert int(measured["cycle"].max()) == 25
        assert len(measured) == 25
    assert shifted == 46
    assert unshifted == 89


# ---------------------------------------------------------------------------
# the defaults, on the real data
# ---------------------------------------------------------------------------

def test_the_default_call_drops_exactly_what_it_says(real_v11_dir,
                                                     exploration_dir):
    default = mc.load_cycle_features(
        data_dir=exploration_dir, v11_dir=real_v11_dir
    )
    filters = default.attrs["filters"]
    assert filters["n_rows_in"] == 114738
    assert filters["n_rows_out"] == len(default)
    assert default["in_analysis_set"].all()
    assert default["is_series_valid"].all()
    assert not default["is_placeholder"].any()
    reasons = dict(
        (line.split(":")[0], line) for line in filters["excluded"]
    )
    assert "cycles past the 0.88 Ah crossing (beyond_crossing)" in reasons
    assert "1179 rows" in reasons[
        "cycles past the 0.88 Ah crossing (beyond_crossing)"
    ]


def test_require_series_valid_removes_171_rows_from_the_v1_0_table(
    real_v11_dir, exploration_dir
):
    """With the test fold in, the difference is exactly the disputed 171."""
    base = mc.load_cycles(clean=True, include_test=True,
                          data_dir=exploration_dir)
    both = mc.load_cycles(clean=True, include_test=True,
                          require_series_valid=True,
                          data_dir=exploration_dir, v11_dir=real_v11_dir)
    assert len(base) - len(both) == C.V11_DISPUTED_CYCLES == 171


def test_load_cycles_default_is_untouched_by_v0_2_0(exploration_dir):
    """The v0.1.1 contract: this call must not have changed."""
    out = mc.load_cycles(data_dir=exploration_dir)
    assert out.attrs["filters"]["applied"]["require_series_valid"] is False
    assert len(out) == 90314


def test_cell_features_on_the_real_cells(real_v11_dir, exploration_dir):
    out = mc.load_cell_features(include_test=True, data_dir=exploration_dir,
                                v11_dir=real_v11_dir)
    assert len(out) == 135
    assert out["n_segments"].sum() == 140
    assert set(out.loc[out["n_segments"] > 1, "cell_uid"]) == set(
        C.V11_CONTINUATION_CELLS
    )
    assert out["n_cycles_total"].sum() == C.V11_STRUCT_CYCLES


def test_counts_helper_matches_the_constants(real_v11_dir, exploration_dir):
    v = mc.v11_counts(data_dir=exploration_dir, v11_dir=real_v11_dir)
    assert v["v11_struct_cycles"] == C.V11_STRUCT_CYCLES
    assert v["v11_analysis_cycles"] == C.V11_ANALYSIS_CYCLES
    assert v["v11_invalid_cycles"] == C.V11_SERIES_INVALID_CYCLES
    assert v["v11_invalid_cells"] == C.V11_SERIES_INVALID_CELLS
    assert v["v11_grid_cycles"] == C.V11_GRID_RANGE_CYCLES
    assert v["v11_grid_cells"] == C.V11_GRID_RANGE_CELLS
    assert v["v11_disputed"] == C.V11_DISPUTED_CYCLES
    assert v["v11_disputed_cells"] == C.V11_DISPUTED_CELLS
    assert v["v11_reverse"] == C.V11_REVERSE_CYCLES
    assert v["v11_both_valid"] == C.V11_BOTH_VALID_CYCLES
    assert v["v11_placeholders"] == C.V11_PLACEHOLDERS
    assert v["v11_cells"] == C.V11_CELLS


def test_describe_runs_against_the_real_index(real_v11_dir, exploration_dir,
                                              capsys):
    mc.describe(data_dir=exploration_dir, v11_dir=real_v11_dir)
    printed = capsys.readouterr().out
    assert "249" in printed                     # the is_series_valid total
    assert "171" in printed                     # the disputed rows
    assert "114,738" in printed
    for name in C.V11_NEW_SERIES_COLUMNS:
        assert name in printed
    for name in C.V11_GRID_FIELDS:
        assert name in printed
    assert "v0.3.0" in printed
    assert C.V11_ZENODO_DOI in printed
    assert "not yet published" not in printed


# ---------------------------------------------------------------------------
# the published files are never written
# ---------------------------------------------------------------------------

def test_the_real_files_are_untouched(real_v11_dir, exploration_dir):
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(real_v11_dir.iterdir()) if path.is_file()
    }
    mc.load_cycle_features(data_dir=exploration_dir, v11_dir=real_v11_dir)
    mc.load_cell_features(data_dir=exploration_dir, v11_dir=real_v11_dir)
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(real_v11_dir.iterdir()) if path.is_file()
    }
    assert before == after


def test_the_real_index_hashes_to_the_manifest_value(real_v11_dir):
    """If this fails, the directory is not the published v1.1 data."""
    from matr_clean import _locate

    for name in C.V11_REQUIRED_FILES:
        assert _locate._sha256(real_v11_dir / name) == C.V11_SHA256[name], name
        assert (real_v11_dir / name).stat().st_size == C.V11_SIZE_BYTES[name], name
