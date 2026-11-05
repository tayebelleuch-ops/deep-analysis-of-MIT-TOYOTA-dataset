"""Shape, columns and argument handling of the three v0.2.0 entry points."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import matr_clean as mc
from matr_clean import constants as C


def _feats(exploration_dir, v11_dir, **kw):
    return mc.load_cycle_features(
        data_dir=exploration_dir, v11_dir=v11_dir, **kw
    )


def test_columns_and_order(exploration_dir, v11_dir):
    out = _feats(exploration_dir, v11_dir, clean=False, require_series_valid=False,
                 beyond_crossing=True, include_test=True)
    expected = (
        list(C.V11_KEY_COLUMNS)
        + ["soh", "cycles_to_eol"]
        + ["is_measured_cycle", "is_artifact_cycle", "is_restart_cycle",
           "is_junction_cycle", "is_clean_cycle"]
        + list(C.V11_STATUS_FLAGS)
        + list(C.V11_COMPONENT_FLAGS)
        + list(C.V11_SERIES_COLUMNS)
    )
    assert list(out.columns) == expected


def test_the_six_new_series_are_present(exploration_dir, v11_dir):
    out = _feats(exploration_dir, v11_dir)
    for name in C.V11_NEW_SERIES_COLUMNS:
        assert name in out.columns
        assert out[name].notna().all(), name


def test_key_is_unique(exploration_dir, v11_dir):
    out = _feats(exploration_dir, v11_dir, clean=False, require_series_valid=False,
                 beyond_crossing=True, include_test=True)
    assert not out.duplicated(["cell_uid", "cycle"]).any()


def test_variables_selects_series_but_never_flags(exploration_dir, v11_dir):
    out = _feats(exploration_dir, v11_dir, variables=("IR_ohm",))
    assert "IR_ohm" in out.columns
    assert "QCharge_Ah" not in out.columns
    # every flag survives, whatever was asked for
    for name in C.V11_STATUS_FLAGS + C.V11_COMPONENT_FLAGS:
        assert name in out.columns
    for name in ("is_clean_cycle", "is_measured_cycle"):
        assert name in out.columns
    assert "cycle" in out.columns and "cell_uid" in out.columns


def test_variables_accepts_a_bare_string(exploration_dir, v11_dir):
    out = _feats(exploration_dir, v11_dir, variables="IR_ohm")
    assert "IR_ohm" in out.columns and "Tavg_C" not in out.columns


def test_unknown_variable_raises_and_names_the_options(exploration_dir, v11_dir):
    with pytest.raises(ValueError) as excinfo:
        _feats(exploration_dir, v11_dir, variables=("Qdlin",))
    message = str(excinfo.value)
    assert "Qdlin" in message
    assert "IR_ohm" in message          # the error says what is available


def test_flag_dtypes(exploration_dir, v11_dir):
    out = _feats(exploration_dir, v11_dir, clean=False, require_series_valid=False,
                 beyond_crossing=True, include_test=True)
    for name in C.V11_STATUS_FLAGS + C.V11_COMPONENT_FLAGS:
        assert out[name].dtype == bool, name
    # the v1.0 flags are nullable, because beyond_crossing rows have no judgement
    assert str(out["is_clean_cycle"].dtype) == "boolean"


def test_batch_date_is_not_returned_source_batch_date_is(exploration_dir, v11_dir):
    """The whole point of the continuation trap: batch_date names the wrong file."""
    out = _feats(exploration_dir, v11_dir)
    assert "source_batch_date" in out.columns
    assert "batch_date" not in out.columns


def test_cell_features_widens_the_cell_table(exploration_dir, v11_dir):
    cells = mc.load_cells(data_dir=exploration_dir)
    out = mc.load_cell_features(
        include_test=True, data_dir=exploration_dir, v11_dir=v11_dir
    )
    assert len(out) == len(cells)
    for name in C.V11_CELL_COLUMNS:
        assert name in out.columns
    # the join is 1:1 and adds exactly the six columns
    assert set(out.columns) == set(cells.columns) | set(C.V11_CELL_COLUMNS)


def test_cell_features_drops_the_test_fold_by_default(exploration_dir, v11_dir):
    kept = mc.load_cell_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert (kept["fold"] != C.TEST_FOLD).all()
    everything = mc.load_cell_features(
        include_test=True, data_dir=exploration_dir, v11_dir=v11_dir
    )
    assert len(everything) > len(kept)
    # load_cells is the inventory view and keeps them; this one does not
    assert len(mc.load_cells(data_dir=exploration_dir)) == len(everything)


def test_conditioning_needs_no_v11_data(exploration_dir):
    """The headline property: policy conditioning works before v1.1 exists."""
    out = mc.load_conditioning(data_dir=exploration_dir)
    assert out["X"].dtype == np.dtype("float32")
    assert out["X"].shape == (len(out["cell_uid"]), 4)
    assert out["fields"] == C.CONDITIONING_FIELDS if hasattr(
        C, "CONDITIONING_FIELDS") else True
    assert len(out["batch_date"]) == len(out["cell_uid"])
    assert len(out["policy_canonical"]) == len(out["cell_uid"])
    assert (out["fold"] != C.TEST_FOLD).all()


def test_conditioning_aligns_row_for_row_with_the_cell_table(exploration_dir):
    cond = mc.load_conditioning(data_dir=exploration_dir)
    cells = mc.load_cells(include_test=False, data_dir=exploration_dir)
    assert list(cond["cell_uid"]) == list(cells["cell_uid"].astype(str))


def test_conditioning_rejects_an_unknown_field(exploration_dir):
    with pytest.raises(ValueError) as excinfo:
        mc.load_conditioning(fields=("not_a_column",), data_dir=exploration_dir)
    assert "not_a_column" in str(excinfo.value)


def test_conditioning_cycle_counts_use_the_index(exploration_dir, v11_dir,
                                                 fixture_cells):
    out = mc.load_conditioning(
        include_cycle_counts=True, data_dir=exploration_dir, v11_dir=v11_dir
    )
    assert "n_cycles" in out and "n_series_invalid" in out
    present = np.isin(out["cell_uid"], list(fixture_cells))
    # cells the fixture covers have rows; the rest are zero, not NaN
    assert out["n_cycles"][present].sum() > 0
    assert (out["n_cycles"][~present] == 0).all()
    assert out["n_cycles"].dtype == np.dtype("int64")


def test_public_api_is_exported():
    for name in ("load_cycle_features", "load_cell_features", "load_conditioning",
                 "v11_counts"):
        assert name in mc.__all__
        assert callable(getattr(mc, name))
    assert mc.__version__ == "0.2.0"
