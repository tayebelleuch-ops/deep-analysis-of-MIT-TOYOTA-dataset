"""The series reader against the real published files, with the real numbers.

Skipped unless ``MATR_CLEAN_TEST_DATA`` names a directory holding the three
``within_cycle_*.h5`` files and the index. Everything here is read-only: the files
are opened ``mode="r"`` and a final test asserts not one size or mtime moved.

These are the assertions that defend ``SPEC_v0.3.md`` section 7.2's published
figures -- 249 / 97, 48 / 32 / 34, 93 across 48, 18 under ``"measured"``, 140 of 140
contiguous blocks, the five two-file cells. The fixture suite in
``tests/test_v11_series.py`` is what CI runs; this is what makes the numbers true.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

import matr_clean as mc
from matr_clean import _h5, constants, features, series

h5py = pytest.importorskip("h5py", reason="the series tests need the 'series' extra")

REAL_DATA_ENV = "MATR_CLEAN_TEST_DATA"


@pytest.fixture(scope="module")
def real_dir():
    raw = os.environ.get(REAL_DATA_ENV)
    if not raw:
        pytest.skip(
            "set {0} to a directory holding the published within_cycle_* files"
            .format(REAL_DATA_ENV)
        )
    directory = Path(raw).expanduser().resolve()
    missing = [
        name for name in constants.V11_ALL_DATA_FILES
        if not (directory / name).is_file()
    ]
    if missing:
        pytest.skip("{0} lacks {1}".format(directory, ", ".join(missing)))
    return directory


@pytest.fixture(scope="module")
def real_index(real_dir, exploration_dir):
    import pandas as pd

    frame = pd.read_csv(real_dir / constants.V11_INDEX_FILE)
    for column in constants.V11_STATUS_FLAGS + constants.V11_COMPONENT_FLAGS:
        frame[column] = frame[column].astype(bool)
    return frame


@pytest.fixture
def load(exploration_dir, real_dir):
    def call(*args, **kwargs):
        kwargs.setdefault("data_dir", str(exploration_dir))
        kwargs.setdefault("v11_dir", str(real_dir))
        return mc.load_series(*args, **kwargs)

    return call


# ---------------------------------------------------------------------------
# the published counts
# ---------------------------------------------------------------------------

def test_row_and_cell_counts(real_index):
    assert len(real_index) == constants.V11_STRUCT_CYCLES == 114738
    assert real_index["cell_uid"].nunique() == constants.V11_CELLS == 135
    assert not real_index.duplicated(["cell_uid", "cycle"]).any()
    assert int(real_index["in_analysis_set"].sum()) == constants.V11_ANALYSIS_CYCLES
    assert int(real_index["beyond_crossing"].sum()) == constants.V11_BEYOND_CROSSING
    assert int(real_index["is_placeholder"].sum()) == constants.V11_PLACEHOLDERS == 46


def test_series_validity_totals(real_index):
    bad = ~real_index["is_series_valid"]
    assert int(bad.sum()) == constants.V11_SERIES_INVALID_CYCLES == 249
    assert real_index.loc[bad, "cell_uid"].nunique() == 97

    grid = ~real_index["series_grid_in_range"]
    assert int(grid.sum()) == constants.V11_GRID_RANGE_CYCLES == 48
    assert real_index.loc[grid, "cell_uid"].nunique() == 32


def test_grid_failures_clean_in_v1_0(real_index, exploration_dir):
    """34 of the 48 are ``is_clean_cycle=True`` -- the summary flag misses them."""
    import pandas as pd

    v10 = pd.read_csv(exploration_dir / constants.CYCLES_FILE,
                      usecols=["cell_uid", "cycle", constants.CLEAN_FLAG])
    merged = real_index[["cell_uid", "cycle", "series_grid_in_range"]].merge(
        v10, on=["cell_uid", "cycle"], how="left"
    )
    failures = merged.loc[~merged["series_grid_in_range"]]
    clean = series._bool_or_false(failures[constants.CLEAN_FLAG])
    assert int(clean.sum()) == constants.V11_GRID_RANGE_CLEAN_IN_V1_0 == 34


def test_placeholders_nest_inside_series_invalid(real_index):
    """One predicate is enough: a placeholder is always series-invalid."""
    assert (real_index["is_placeholder"] == ~real_index["series_present"]).all()
    assert (~real_index.loc[real_index["is_placeholder"], "is_series_valid"]).all()
    placeholders = real_index.loc[real_index["is_placeholder"]]
    assert set(placeholders["cycle"]) == {1}
    assert set(placeholders["source_batch_date"]) == {"2017-05-12"}


def test_the_extremes_are_where_the_spec_says(real_index):
    worst_low = real_index.loc[real_index["Qdlin_min"].idxmin()] \
        if "Qdlin_min" in real_index else None
    if worst_low is None:  # pragma: no cover - the index always has it
        pytest.skip("this index has no Qdlin_min column")
    assert worst_low["cell_uid"] == "EL150800737364"
    assert int(worst_low["cycle"]) == 368
    assert worst_low["Qdlin_min"] == pytest.approx(-4030.3, abs=0.5)

    worst_high = real_index.loc[real_index["Qdlin_max"].idxmax()]
    assert worst_high["cell_uid"] == "EL150800460511"
    assert int(worst_high["cycle"]) == 247
    assert worst_high["Qdlin_max"] == pytest.approx(1430.7, abs=0.5)

    hottest = real_index.loc[real_index["Tdlin_max"].idxmax()]
    assert hottest["cell_uid"] == "EL150800460653"
    assert int(hottest["cycle"]) == 163
    assert hottest["Tdlin_max"] == pytest.approx(2089.2, abs=0.5)
    # and it fails only the grid check, so no summary-level flag catches it
    failing = [
        name for name in constants.V11_COMPONENT_FLAGS if not hottest[name]
    ]
    assert failing == ["series_grid_in_range"]


# ---------------------------------------------------------------------------
# the structural invariant the reader rests on
# ---------------------------------------------------------------------------

def test_h5_row_blocks_are_contiguous(real_index):
    """140 of 140: a cell's rows inside one file are one ascending block.

    This is what licenses every read in ``_h5.py`` being a single slice, so it is
    asserted rather than assumed.
    """
    groups = 0
    for _, block in real_index.groupby(["cell_uid", "source_batch_date"]):
        rows = block.sort_values("cycle")["h5_row"].to_numpy().astype(np.int64)
        assert (np.diff(rows) == 1).all(), "ascending and contiguous"
        assert rows[-1] - rows[0] + 1 == len(rows)
        groups += 1
    assert groups == constants.V11_STRUCT_ROWS == 140


def test_h5_row_addresses_the_row_it_claims(real_index, real_dir,
                                            exploration_dir):
    """All 114,738 rows: the index's ``h5_row`` really is that cell and cycle."""
    checked = 0
    for date in sorted(constants.V11_H5_FILES):
        sub = real_index.loc[real_index["source_batch_date"] == date]
        with mc.open_batch(date, data_dir=str(exploration_dir),
                           v11_dir=str(real_dir)) as handle:
            n = handle["row/cycle"].shape[0]
            uids, cycles = _h5.row_keys(handle, 0, n)
        rows = sub["h5_row"].to_numpy().astype(np.int64)
        assert (uids[rows] == sub["cell_uid"].to_numpy()).all()
        assert (cycles[rows] == sub["cycle"].to_numpy()).all()
        checked += len(sub)
    assert checked == constants.V11_STRUCT_CYCLES


def test_per_file_shapes(real_dir, exploration_dir):
    expected = {
        "2017-05-12": (38811, 38812, 40951666),
        "2017-06-30": (24920, 24921, 32094849),
        "2018-04-12": (51007, 51008, 38822223),
    }
    total_native = 0
    for date, (rows, offsets, native) in expected.items():
        with mc.open_batch(date, data_dir=str(exploration_dir),
                           v11_dir=str(real_dir)) as handle:
            assert handle.attrs == {} or len(dict(handle.attrs)) == 0
            for field in constants.V11_GRID_FIELDS:
                ds = handle["grid"][field]
                assert ds.shape == (rows, 1000)
                assert ds.dtype == np.dtype("float32")
                assert ds.chunks == (64, 1000)
                assert ds.compression == "gzip" and ds.compression_opts == 4
                assert ds.shuffle is True
            assert handle["native/offset"].shape == (offsets,)
            assert handle["native/offset"].chunks is None
            assert handle["row/cycle"].dtype == np.dtype("int32")
            assert handle["row/cell_uid"].dtype == np.dtype("S16")
            assert handle["vdlin"].dtype == np.dtype("float64")
            for field in ("I", "V", "T", "Qc", "Qd"):
                ds = handle["native"][field]
                assert ds.shape == (native,)
                assert ds.dtype == np.dtype("float32")
                assert ds.chunks == (65536,)
            assert handle["native/t"].dtype == np.dtype("float64")
            total_native += native
    assert total_native == 111868738


def test_vdlin_is_identical_in_all_three_files(real_dir, exploration_dir):
    grids = []
    for date in sorted(constants.V11_H5_FILES):
        with mc.open_batch(date, data_dir=str(exploration_dir),
                           v11_dir=str(real_dir)) as handle:
            grids.append(_h5.vdlin_of(handle))
    assert all(np.array_equal(grids[0], g) for g in grids[1:])
    differing = int((np.abs(grids[0] - np.linspace(3.5, 2.0, 1000)) > 0).sum())
    assert differing == 15


# ---------------------------------------------------------------------------
# the five continuation cells
# ---------------------------------------------------------------------------

EXPECTED_SEAMS = {
    "EL150800460486": (1178, 1179, 2159),
    "EL150800460514": (1189, 1190, 1851),
    "EL150800460623": (1176, 1177, 2236),
    "EL150800464865": (1226, 1227, 1708),
    "EL150800464977": (1225, 1226, 1433),
}


def test_five_two_file_cells(real_index):
    spanning = real_index.groupby("cell_uid")["source_batch_date"].nunique()
    multi = sorted(spanning[spanning > 1].index)
    assert multi == sorted(constants.V11_CONTINUATION_CELLS)
    assert len(multi) == 5
    assert multi == sorted(EXPECTED_SEAMS)


@pytest.mark.parametrize("uid", sorted(EXPECTED_SEAMS))
def test_seam_dispatches_on_source_batch_date(load, uid):
    last_a, first_b, last_b = EXPECTED_SEAMS[uid]
    out = load(uid, cycles=[last_a, first_b], fields=("Qdlin",),
               include_test=True)
    assert out["present"][0].all()
    assert list(out["segment"][0]) == [1, 2]
    assert list(out["source_batch_date"][0]) == ["2017-05-12", "2017-06-30"]
    assert out["batch_date"][0] == "2017-05-12"
    assert len(out["filters"]["files_read"]) == 2
    assert not np.isnan(out["Qdlin"][0]).any()


@pytest.mark.parametrize("uid", sorted(EXPECTED_SEAMS))
def test_full_series_of_a_continuation_cell_spans_two_files(load, uid):
    out = load(uid, cycles=None, fields=("Qdlin",), include_test=True,
               beyond_crossing=True)
    dates = sorted(set(out["source_batch_date"][out["present"]]))
    assert dates == ["2017-05-12", "2017-06-30"]
    labels = out["cycle"][0][out["present"][0]]
    assert labels.max() == EXPECTED_SEAMS[uid][2]
    assert (np.diff(labels) == 1).all(), "the seam leaves no gap in the labels"


# ---------------------------------------------------------------------------
# the early-window figures, both conventions
# ---------------------------------------------------------------------------

def _measured_labels(index, uid, n):
    own = index.loc[index["cell_uid"] == uid].sort_values("cycle")
    return own.loc[~own["is_placeholder"], "cycle"].to_numpy()[:n]


@pytest.mark.parametrize("n,masked,cells", [(10, 56, 47), (25, 93, 48),
                                            (50, 118, 48)])
def test_labels_window_masks_and_cells(load, n, masked, cells):
    out = load(cycles=range(1, n + 1), fields=constants.V11_GRID_FIELDS,
               include_test=True)
    assert out["cell_uid"].shape == (135,)
    assert out["cycle"].shape == (135, n)
    bad = out["present"] & ~out["valid"]
    assert int(bad.sum()) + int((~out["present"]).sum()) == masked
    assert int((bad | ~out["present"]).any(axis=1).sum()) == cells
    assert int(out["is_placeholder"].sum()) == 46
    nan_positions = sum(
        int(np.isnan(out[f]).all(axis=2).sum()) for f in constants.V11_GRID_FIELDS
    )
    assert nan_positions == 46 * 3 == 138


@pytest.mark.parametrize("n,masked,cells", [(10, 11, 2), (25, 48, 18),
                                            (50, 73, 18)])
def test_measured_window_masks_and_cells(load, real_index, n, masked, cells):
    """Under ``"measured"`` there is no NaN at all -- nothing for nan_to_num to do."""
    total_masked = 0
    affected = 0
    nan_rows = 0
    uids = sorted(set(real_index["cell_uid"]))
    for uid in uids:
        labels = _measured_labels(real_index, uid, n)
        out = load(uid, cycles=[int(x) for x in labels],
                   fields=constants.V11_GRID_FIELDS, include_test=True,
                   beyond_crossing=True)
        bad = int((out["present"] & ~out["valid"]).sum())
        total_masked += bad
        affected += 1 if bad else 0
        nan_rows += sum(
            int(np.isnan(out[f]).all(axis=2).sum())
            for f in constants.V11_GRID_FIELDS
        )
    assert total_masked == masked
    assert affected == cells
    assert nan_rows == 0


def test_measured_window_drop_invalid_cells_removes_eighteen(load, real_index):
    removed = 0
    for uid in sorted(set(real_index["cell_uid"])):
        labels = [int(x) for x in _measured_labels(real_index, uid, 25)]
        out = load(uid, cycles=labels, fields=("Qdlin",), include_test=True,
                   beyond_crossing=True)
        if (out["present"] & ~out["is_series_valid"]).any():
            removed += 1
    assert removed == 18


def test_in_window_out_of_band_is_six_positions_four_of_them_qdlin(real_index):
    """Section 1.13's correction, asserted.

    Six positions in labels 1-25 fail ``series_grid_in_range``; only four carry an
    out-of-band ``Qdlin``. The other two fail on another channel.
    """
    window = real_index.loc[real_index["cycle"] <= 25]
    failures = window.loc[~window["series_grid_in_range"]]
    assert len(failures) == 6
    assert failures["cell_uid"].nunique() == 6
    big = failures.loc[failures["Qdlin_max"] > 5.0]
    assert len(big) == 4
    assert sorted(big["cell_uid"]) == [
        "EL150800463871", "EL150800464002", "EL150800464865", "EL150800464977",
    ]
    assert window["Qdlin_max"].max() == pytest.approx(48.8, abs=0.2)
    assert window["Qdlin_min"].min() == pytest.approx(-9.73, abs=0.05)
    assert window["Tdlin_max"].max() < 45.0, "no thermal extreme inside 25 cycles"


def test_twelve_thirteen_cluster_is_sixteen_cells(real_index):
    """Section 1.12's correction: 17 cycles across 16 cells, not 18 / 40-of-46."""
    batch = real_index.loc[real_index["source_batch_date"] == "2017-05-12"]
    cluster = batch.loc[batch["cycle"].isin([12, 13]) & ~batch["is_series_valid"]]
    assert len(cluster) == 17
    assert cluster["cell_uid"].nunique() == 16


# ---------------------------------------------------------------------------
# alignment, and the whole-dataset read path
# ---------------------------------------------------------------------------

def test_alignment_with_conditioning_on_real_data(load, exploration_dir):
    cond = mc.load_conditioning(data_dir=str(exploration_dir))
    out = load(cycles=[10], fields=("Qdlin",))
    assert list(out["cell_uid"]) == list(cond["cell_uid"])
    assert len(out["cell_uid"]) == 108


def test_full_window_reads_all_three_files_once(load, monkeypatch):
    opened = []
    real = _h5.open_batch_file

    def spy(directory, date, func_name="open_batch"):
        opened.append(str(date))
        return real(directory, date, func_name)

    monkeypatch.setattr(_h5, "open_batch_file", spy)
    out = load(cycles=range(1, 26), fields=constants.V11_GRID_FIELDS,
               include_test=True)
    assert sorted(opened) == sorted(constants.V11_H5_FILES)
    assert len(opened) == 3, "each file opened exactly once"
    assert out["Qdlin"].shape == (135, 25, 1000)


def test_native_lengths_match_n_samples(load, real_index):
    uid = "EL150800460514"
    out = load(uid, cycles=range(1, 11), fields=constants.V11_NATIVE_FIELDS,
               include_test=True)
    for k in range(10):
        expected = int(out["n_samples"][0, k])
        for field in constants.V11_NATIVE_FIELDS:
            assert len(out[field][0][k]) == expected


# ---------------------------------------------------------------------------
# nothing is written
# ---------------------------------------------------------------------------

def test_the_integration_run_changes_no_file(load, real_dir):
    before = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(real_dir.iterdir()) if p.is_file()
    }
    load("EL150800460514", cycles=range(1, 6),
         fields=constants.V11_GRID_FIELDS + constants.V11_NATIVE_FIELDS,
         include_test=True)
    mc.load_vdlin(v11_dir=str(real_dir))
    after = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(real_dir.iterdir()) if p.is_file()
    }
    assert before == after
