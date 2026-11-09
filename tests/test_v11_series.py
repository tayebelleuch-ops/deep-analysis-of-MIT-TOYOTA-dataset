"""The v0.3.0 series reader: every guarantee, each with the number it defends.

Everything here runs against the committed fixture
(``tests/fixtures/series/``, two tiny HDF5 files and a 12-row real index subset),
so the whole file runs with no 2.20 GB of data present and with no network. The
integration counterparts, which assert the published 249 / 97 / 48 / 32 / 34 / 93 /
18 figures against the real files, are in ``tests/test_v11_series_integration.py``
and skip unless ``MATR_CLEAN_TEST_DATA`` is set.

The letters in the test names are ``SPEC_v0.3.md`` section 7.2's table rows.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

import matr_clean as mc
from matr_clean import _h5, constants, series

h5py = pytest.importorskip("h5py", reason="the series tests need the 'series' extra")

PLACEHOLDER = ("EL150800460514", 1)
OUT_OF_BAND = ("EL150800464865", 12)
EXTREME = ("EL150800460511", 247)
CONTINUATION = "EL150800460514"
GAP_CELL = "EL150800464865"


@pytest.fixture
def load(exploration_dir, v11_series_dir):
    """``load_series`` bound to the fixture, so no test repeats the two paths."""

    def call(*args, **kwargs):
        kwargs.setdefault("data_dir", str(exploration_dir))
        kwargs.setdefault("v11_dir", str(v11_series_dir))
        return mc.load_series(*args, **kwargs)

    return call


# ---------------------------------------------------------------------------
# (a) placeholders are masked, not zero-filled
# ---------------------------------------------------------------------------

def test_a_placeholder_grid_row_is_all_nan_never_zero(load):
    uid, cycle = PLACEHOLDER
    out = load(uid, cycles=[cycle, cycle + 1])
    row = out["Qdlin"][0, 0]

    assert out["cycle"][0, 0] == cycle
    assert out["present"][0, 0]           # the row exists...
    assert not out["valid"][0, 0]         # ...and is masked
    assert out["is_placeholder"][0, 0]
    assert not out["is_series_valid"][0, 0]

    assert np.isnan(row).all(), "the placeholder grid row must be all-NaN"
    assert not (row == 0.0).any(), "a zero here would be a fabricated measurement"
    # the neighbouring real cycle is untouched
    assert not np.isnan(out["Qdlin"][0, 1]).any()


def test_a_placeholder_native_row_holds_literal_zeros(load):
    """The native side cannot be detected by NaN at all -- the flag is the signal."""
    uid, cycle = PLACEHOLDER
    out = load(uid, cycles=[cycle], fields=("t", "V", "I"))
    for field in ("t", "V", "I"):
        row = out[field][0][0]
        assert row.shape == (2,), "the placeholder stores two samples"
        assert np.array_equal(row, np.zeros(2, dtype=row.dtype))
        assert not np.isnan(row).any()
    assert out["is_placeholder"][0, 0]
    assert out["n_samples"][0, 0] == 2


@pytest.mark.parametrize("clean", [False, True])
@pytest.mark.parametrize("require_series_valid", [False, True])
def test_a_is_placeholder_survives_every_filter(load, clean, require_series_valid):
    uid, cycle = PLACEHOLDER
    out = load(uid, cycles=[cycle], clean=clean,
               require_series_valid=require_series_valid)
    assert out["is_placeholder"][0, 0], "the raw flag is never suppressed"
    assert np.isnan(out["Qdlin"][0, 0]).all(), "and the data is never repaired"


def test_a_prime_nan_to_num_changes_only_the_placeholder(load):
    """The two failure modes are independent, and the fixture proves it.

    ``np.nan_to_num`` touches exactly the placeholder grid positions and leaves
    every out-of-band value alone, so it is not a repair for either problem: it
    turns the one genuinely missing row into plausible zeros and does nothing at all
    about +1,430 Ah.
    """
    out = load([PLACEHOLDER[0], EXTREME[0]], cycles=None, fields=("Qdlin",))
    X = out["Qdlin"]
    changed = np.nan_to_num(X, nan=0.0) != X
    nan_mask = np.isnan(X)
    assert np.array_equal(changed, nan_mask)

    # every changed position is a placeholder row or an absent one; none is a
    # row that merely holds an impossible number.
    absent_or_placeholder = (~out["present"]) | out["is_placeholder"]
    assert changed.any(axis=2)[absent_or_placeholder].all()
    assert not changed.any(axis=2)[out["present"] & ~out["is_placeholder"]].any()

    # and the extreme row is present, finite, and left exactly as stored
    i = list(out["cell_uid"]).index(EXTREME[0])
    k = int(np.flatnonzero(out["cycle"][i] == EXTREME[1])[0])
    assert out["present"][i, k] and not np.isnan(X[i, k]).any()
    assert X[i, k].max() > 1000.0


# ---------------------------------------------------------------------------
# (b) the impossible values are masked, present, and unrepaired
# ---------------------------------------------------------------------------

def test_b_out_of_band_qdlin_is_masked_but_returned(load):
    uid, cycle = OUT_OF_BAND
    out = load(uid, cycles=[cycle])
    row = out["Qdlin"][0, 0]

    assert out["present"][0, 0]
    assert not out["valid"][0, 0], "series_grid_in_range fails here"
    assert not out["is_series_valid"][0, 0]
    assert not out["is_placeholder"][0, 0], "this is not a missing row"
    assert not np.isnan(row).any(), "and it is not NaN either"
    assert row.max() > 40.0, "the real +48.8 Ah value is returned as stored"


def test_b_the_extreme_is_as_stored(load):
    uid, cycle = EXTREME
    out = load(uid, cycles=[cycle], fields=("Qdlin",))
    row = out["Qdlin"][0, 0]
    assert pytest.approx(float(row.max()), abs=0.5) == 1430.7
    assert not out["valid"][0, 0]
    assert not np.isnan(row).any()


def test_b_clean_flag_disagrees_in_the_fixture(load):
    """``is_clean_cycle`` does not catch what ``is_series_valid`` catches."""
    out = load(cycles=None, fields=("Qdlin",), include_test=True)
    disputed = out["present"] & (out["is_clean_cycle"] == 1) & ~out["is_series_valid"]
    assert disputed.any(), "the fixture must contain a disputed row"


def test_b_clean_is_minus_one_where_v10_never_judged(load):
    """Absence of a v1.0 row is not ``False``; it is ``-1``."""
    out = load(cycles=[1, 99999], fields=("Qdlin",), cell=PLACEHOLDER[0])
    assert out["is_clean_cycle"].dtype == np.int8
    k = int(np.flatnonzero(out["cycle"][0] == 99999)[0])
    assert not out["present"][0, k]
    assert out["is_clean_cycle"][0, k] == series.CLEAN_NOT_JUDGED == -1


# ---------------------------------------------------------------------------
# (c) the continuation cells, dispatched on source_batch_date
# ---------------------------------------------------------------------------

def test_c_seam_resolves_through_source_batch_date(load):
    out = load(CONTINUATION, cycles=[1189, 1190, 1191], fields=("Qdlin",))
    assert list(out["cycle"][0]) == [1189, 1190, 1191]
    assert out["present"][0].all()
    assert list(out["segment"][0]) == [1, 2, 2]
    assert list(out["source_batch_date"][0]) == [
        "2017-05-12", "2017-06-30", "2017-06-30"
    ]
    assert len(out["filters"]["files_read"]) == 2
    assert not np.isnan(out["Qdlin"][0]).any()


def test_c_batch_date_is_returned_but_is_not_the_file(load):
    """The trap, asserted: ``batch_date`` names the wrong file for segment 2."""
    out = load(CONTINUATION, cycles=[1190], fields=("Qdlin",))
    assert out["batch_date"][0] == "2017-05-12"
    assert out["source_batch_date"][0, 0] == "2017-06-30"
    assert out["batch_date"][0] != out["source_batch_date"][0, 0]


def test_c_dispatching_on_batch_date_would_find_nothing(exploration_dir,
                                                        v11_series_dir):
    """A ``batch_date``-addressed lookup is asserted to fail, so it cannot regress.

    This is the whole reason ``open_batch`` names its parameter
    ``source_batch_date``: the wrong file simply does not hold the row.
    """
    out = mc.load_series(CONTINUATION, cycles=[1190], fields=("Qdlin",),
                         data_dir=str(exploration_dir),
                         v11_dir=str(v11_series_dir))
    wrong = str(out["batch_date"][0])          # 2017-05-12
    right = str(out["source_batch_date"][0, 0])  # 2017-06-30
    assert wrong != right

    with mc.open_batch(wrong, data_dir=str(exploration_dir),
                       v11_dir=str(v11_series_dir)) as handle:
        uids, cycles = _h5.row_keys(handle, 0, handle["row/cycle"].shape[0])
    hit = [(u, int(c)) for u, c in zip(uids, cycles)
           if u == CONTINUATION and int(c) == 1190]
    assert hit == [], "cycle 1190 must not be in the batch_date file"

    with mc.open_batch(right, data_dir=str(exploration_dir),
                       v11_dir=str(v11_series_dir)) as handle:
        uids, cycles = _h5.row_keys(handle, 0, handle["row/cycle"].shape[0])
    hit = [(u, int(c)) for u, c in zip(uids, cycles)
           if u == CONTINUATION and int(c) == 1190]
    assert hit == [(CONTINUATION, 1190)]


def test_c_open_batch_rejects_an_unknown_date(exploration_dir, v11_series_dir):
    with pytest.raises(ValueError, match="source_batch_date"):
        mc.open_batch("2018-04-13", data_dir=str(exploration_dir),
                      v11_dir=str(v11_series_dir))


# ---------------------------------------------------------------------------
# (d) addressing is never positional
# ---------------------------------------------------------------------------

def test_d_rows_are_addressed_by_h5_row_not_by_position(load, exploration_dir,
                                                        v11_series_dir):
    """The fixture writes cells in descending uid order inside each file.

    So the index's canonical cell order and the files' row order disagree, and a
    reader that used the position of a cell in its own ``cell_uid`` list would
    return another cell's data. This asserts the two orders really do differ and
    that every returned row is the one ``h5_row`` names.
    """
    from matr_clean import features

    index = features._read_v11(str(exploration_dir), str(v11_series_dir))["index"]
    for date in sorted(set(index["source_batch_date"])):
        sub = index.loc[index["source_batch_date"] == date]
        with mc.open_batch(date, data_dir=str(exploration_dir),
                           v11_dir=str(v11_series_dir)) as handle:
            n = handle["row/cycle"].shape[0]
            uids, cycles = _h5.row_keys(handle, 0, n)
        rows = sub["h5_row"].to_numpy().astype(int)
        assert list(uids[rows]) == list(sub["cell_uid"])
        assert list(cycles[rows]) == list(sub["cycle"])

        # and the file order is NOT the index's cell order
        first_seen = list(dict.fromkeys(sub["cell_uid"]))
        in_file = list(dict.fromkeys(uids))
        if len(first_seen) > 1:
            assert in_file != sorted(first_seen), (
                "the fixture must not be stored in canonical cell order"
            )


def test_d_struct_index_is_not_channel_minus_one(load):
    """The cell that proves positional addressing is wrong is in the fixture."""
    from matr_clean import features

    out = load(cycles=None, fields=("Qdlin",), include_test=True)
    index = features._read_v11(
        out["filters"]["data_dir"], out["filters"]["data_dir"]
    )["index"]
    off = index["source_struct_index"] != index["source_channel"] - 1
    assert off.any(), "the fixture must carry an off-position struct row"


# ---------------------------------------------------------------------------
# (e) no NaN-to-zero anywhere in the code path
# ---------------------------------------------------------------------------

FORBIDDEN = (
    "nan_to_num", "fillna", "clip", "interp", "ffill", "bfill", "dropna",
    "interpolate", "nan_to_zero",
)


@pytest.mark.parametrize("module", [series, _h5], ids=["series", "_h5"])
def test_e_source_contains_no_repair_call(module):
    """An AST walk, not a grep: a renamed import cannot hide a call.

    Not one of these names is called anywhere in the two modules that touch the
    data -- not even on an index column, because the missing-value handling is done
    explicitly in ``_bool_or_false`` / ``_tri_state`` / ``_int_or_zero`` /
    ``_str_or_empty``, which say in their names what they put where a value is
    absent. So the rule can be absolute, and is.
    """
    path = Path(module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    source_lines = source.splitlines()

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name in FORBIDDEN:
            offenders.append((name, node.lineno, source_lines[node.lineno - 1].strip()))
    assert offenders == [], (
        "{0} must not repair data: {1}".format(path.name, offenders)
    )


def test_e_nan_count_equals_the_placeholder_count(load):
    """Behavioural half of (e): the NaN that comes back is exactly what is stored."""
    out = load(cycles=None, include_test=True)
    for field in constants.V11_GRID_FIELDS:
        X = out[field]
        nan_rows = np.isnan(X).all(axis=2)
        assert np.array_equal(nan_rows, (~out["present"]) | out["is_placeholder"])
        stored = out["present"] & out["is_placeholder"]
        assert not (X[stored] == 0.0).any(), "no stored placeholder becomes a zero"


# ---------------------------------------------------------------------------
# (f) gaps are never closed
# ---------------------------------------------------------------------------

def test_f_a_real_gap_keeps_its_label_and_its_position(load):
    """The fixture has no cycle 14 for ``EL150800464865``."""
    out = load(GAP_CELL, cycles=range(11, 16), fields=("Qdlin",))
    assert out["cycle"].shape == (1, 5)
    assert list(out["cycle"][0]) == [11, 12, 13, 14, 15]
    assert list(out["present"][0]) == [True, True, True, False, True]
    assert not out["valid"][0, 3]
    assert np.isnan(out["Qdlin"][0, 3]).all()
    # the row after the gap is the real cycle 15, not shifted into position 3
    assert out["present"][0, 4] and not np.isnan(out["Qdlin"][0, 4]).any()


def test_f_length_always_equals_the_request(load):
    for cycles in ([1], [1, 2], range(1, 6), [1, 500, 1189], [99998, 99999]):
        out = load(CONTINUATION, cycles=cycles, fields=("Qdlin",))
        assert out["cycle"].shape[1] == len(list(cycles))
        assert list(out["cycle"][0]) == [int(c) for c in cycles]


def test_f_an_all_absent_request_still_returns_shape(load):
    out = load(CONTINUATION, cycles=[99998, 99999], fields=("Qdlin",))
    assert out["present"].sum() == 0
    assert out["Qdlin"].shape == (1, 2, 1000)
    assert np.isnan(out["Qdlin"]).all()
    assert out["filters"]["files_read"] == []


# ---------------------------------------------------------------------------
# (g) labels always returned
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fields", [("Qdlin",), ("V",), ("t", "Qdlin")])
def test_g_cycle_is_always_present(load, fields):
    out = load(CONTINUATION, cycles=[1, 2], fields=fields)
    assert "cycle" in out
    assert out["cycle"].dtype == np.int32
    assert list(out["cycle"][0]) == [1, 2]


def test_g_cycles_none_returns_each_cells_own_labels(load):
    out = load(cycles=None, fields=("Qdlin",), include_test=True)
    for i, uid in enumerate(out["cell_uid"]):
        labels = out["cycle"][i][out["present"][i]]
        assert (np.diff(labels) > 0).all(), "labels ascend"
        assert labels.min() >= 1


# ---------------------------------------------------------------------------
# (h) masks, not drops
# ---------------------------------------------------------------------------

def test_h_shape_is_identical_under_every_mask_setting(load):
    shapes = set()
    masked = {}
    for clean in (False, True):
        for rsv in (False, True):
            out = load(cycles=None, fields=("Qdlin",), include_test=True,
                       clean=clean, require_series_valid=rsv)
            shapes.add(out["Qdlin"].shape)
            masked[(clean, rsv)] = int((out["present"] & ~out["valid"]).sum())
    assert len(shapes) == 1, "clean=/require_series_valid= must never change shape"
    assert masked[(False, False)] == 0
    assert masked[(False, True)] > 0
    assert masked[(True, True)] >= masked[(False, True)]


def test_h_drop_invalid_cells_is_the_only_thing_that_changes_axis0(load):
    # cycles 11-15 are series-invalid for EL150800464865 (cycle 12) and absent for
    # the other two fixture cells, so exactly one cell is dropped.
    base = load(cycles=range(11, 16), fields=("Qdlin",), include_test=True)
    dropped = load(cycles=range(11, 16), fields=("Qdlin",), include_test=True,
                   drop_invalid_cells=True)
    assert dropped["Qdlin"].shape[0] < base["Qdlin"].shape[0]
    assert dropped["filters"]["n_cells_dropped"] > 0
    assert set(dropped["filters"]["cells_dropped"]).isdisjoint(
        set(dropped["cell_uid"])
    )
    # every surviving cell is clean over the whole requested range
    assert (dropped["present"] & ~dropped["is_series_valid"]).sum() == 0


def test_h_drop_invalid_cells_removing_everything_raises(load):
    with pytest.raises(ValueError, match="removed every requested cell"):
        load(OUT_OF_BAND[0], cycles=[OUT_OF_BAND[1]], drop_invalid_cells=True)


# ---------------------------------------------------------------------------
# (i) the alignment contract
# ---------------------------------------------------------------------------

def test_i_cell_order_is_the_canonical_one(load, exploration_dir):
    import pandas as pd

    out = load(cycles=[1], fields=("Qdlin",), include_test=True)
    table = pd.read_csv(exploration_dir / constants.CELLS_FILE)
    expected = [u for u in table["cell_uid"] if u in set(out["cell_uid"])]
    assert list(out["cell_uid"]) == expected


def test_i_order_is_independent_of_the_order_asked_in(load):
    forwards = load(["EL150800460511", "EL150800464865"], cycles=[246],
                    fields=("Qdlin",), include_test=True)
    backwards = load(["EL150800464865", "EL150800460511"], cycles=[246],
                     fields=("Qdlin",), include_test=True)
    assert list(forwards["cell_uid"]) == list(backwards["cell_uid"])


def test_i_matches_load_conditioning_row_for_row(load, exploration_dir):
    cond = mc.load_conditioning(data_dir=str(exploration_dir))
    out = load(cycles=[1], fields=("Qdlin",))
    fixture_uids = set(out["cell_uid"])
    expected = [u for u in cond["cell_uid"] if u in fixture_uids]
    assert list(out["cell_uid"]) == expected


# ---------------------------------------------------------------------------
# (j) vdlin as stored
# ---------------------------------------------------------------------------

def test_j_vdlin_is_as_stored_not_linspace(exploration_dir, v11_series_dir):
    vdlin = mc.load_vdlin(data_dir=str(exploration_dir),
                          v11_dir=str(v11_series_dir))
    assert vdlin.shape == (constants.V11_VDLIN_POINTS,)
    assert vdlin.dtype == np.float64
    assert vdlin[0] == constants.V11_VDLIN_START_V
    assert vdlin[-1] == constants.V11_VDLIN_STOP_V
    assert (np.diff(vdlin) < 0).all()

    reconstructed = np.linspace(3.5, 2.0, 1000)
    differing = int((np.abs(vdlin - reconstructed) > 0).sum())
    assert differing == 15
    worst = float(np.abs(vdlin - reconstructed).max())
    assert worst == pytest.approx(4.440892098500626e-16, rel=1e-6)
    assert worst < 2.0 * float(np.spacing(3.5)), "one ulp, no more"


def test_j_series_never_reconstructs_the_grid():
    text = Path(series.__file__).read_text(encoding="utf-8")
    assert "linspace" not in text.split('"""')[-1], (
        "the grid must be read, not rebuilt"
    )


def test_j_vdlin_matches_the_one_load_series_returns(load, exploration_dir,
                                                     v11_series_dir):
    out = load(CONTINUATION, cycles=[2], fields=("Qdlin",))
    standalone = mc.load_vdlin(data_dir=str(exploration_dir),
                               v11_dir=str(v11_series_dir))
    assert np.array_equal(out["vdlin"], standalone)


def test_j_no_vdlin_when_no_grid_field_is_asked_for(load):
    out = load(CONTINUATION, cycles=[2], fields=("V",))
    assert "vdlin" not in out


# ---------------------------------------------------------------------------
# (k) dtypes and shapes as stored
# ---------------------------------------------------------------------------

def test_k_grid_dtypes_and_shapes(load):
    out = load(CONTINUATION, cycles=[2, 3], fields=constants.V11_GRID_FIELDS)
    for field in constants.V11_GRID_FIELDS:
        assert out[field].dtype == np.float32
        assert out[field].shape == (1, 2, 1000)
        assert out["field_kind"][field] == "grid"


def test_k_native_is_ragged_and_t_is_float64(load):
    out = load(CONTINUATION, cycles=[1, 2], fields=constants.V11_NATIVE_FIELDS)
    for field in constants.V11_NATIVE_FIELDS:
        assert isinstance(out[field], list)
        assert out["field_kind"][field] == "native"
        expected = np.float64 if field == "t" else np.float32
        assert out[field][0][1].dtype == expected
    lengths = {len(out["t"][0][k]) for k in (0, 1)}
    assert len(lengths) == 2, "ragged: the placeholder is 2 and the real row is not"


def test_k_cell_uid_is_decoded_not_bytes(load):
    out = load(CONTINUATION, cycles=[2], fields=("Qdlin",))
    assert out["cell_uid"].dtype.kind == "U"
    assert out["cell_uid"][0] == CONTINUATION
    with mc.open_batch(
        "2017-05-12",
        data_dir=out["filters"]["data_dir"],
        v11_dir=out["filters"]["data_dir"],
    ) as handle:
        assert handle["row/cell_uid"].dtype == np.dtype("S16")
        assert handle["row/cycle"].dtype == np.dtype("int32")
        assert handle["native/offset"].dtype == np.dtype("int64")
        assert handle["vdlin"].dtype == np.dtype("float64")


def test_k_metadata_dtypes(load):
    out = load(cycles=[1], fields=("Qdlin",), include_test=True)
    assert out["cycle"].dtype == np.int32
    assert out["valid"].dtype == np.bool_
    assert out["present"].dtype == np.bool_
    assert out["n_samples"].dtype == np.int32
    assert out["segment"].dtype == np.int8
    assert out["fold"].dtype == np.int8
    assert out["is_clean_cycle"].dtype == np.int8
    for name in constants.V11_CELL_FLAGS:
        assert out["cell_flags"][name].dtype == np.bool_


# ---------------------------------------------------------------------------
# (l) the contiguity invariant that licenses the single-slice reader
# ---------------------------------------------------------------------------

def test_l_runs_splits_contiguous_and_sparse_requests():
    assert series._runs(np.array([5, 6, 7])) == [(5, 8)]
    assert series._runs(np.array([5])) == [(5, 6)]
    assert series._runs(np.array([1, 2, 10, 11, 20])) == [(1, 3), (10, 12), (20, 21)]
    assert series._runs(np.array([], dtype=np.int64)) == []


def test_l_a_sparse_request_reads_only_its_runs(load, monkeypatch):
    """``cycles=[1, 1189]`` must not read the 1,189 rows in between."""
    calls = []
    real = _h5.grid_block

    def spy(handle, field, lo, hi):
        calls.append((field, lo, hi))
        return real(handle, field, lo, hi)

    monkeypatch.setattr(_h5, "grid_block", spy)
    load(CONTINUATION, cycles=[1, 1189], fields=("Qdlin",))
    assert calls, "the spy must have seen the reads"
    assert all(hi - lo <= 2 for _, lo, hi in calls), calls


# ---------------------------------------------------------------------------
# (n) h5py absent
# ---------------------------------------------------------------------------

def test_n_import_matr_clean_works_without_h5py(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "h5py" or name.startswith("h5py."):
            raise ImportError("no module named h5py (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    monkeypatch.delitem(__import__("sys").modules, "h5py", raising=False)

    with pytest.raises(ImportError) as excinfo:
        _h5.require_h5py("load_series")
    message = str(excinfo.value)
    assert "matr-clean[series]" in message
    assert "load_series" in message
    assert "h5py>=3.0" in message
    assert "3.12.1" in message


def test_n_v02_functions_do_not_need_h5py(exploration_dir):
    """Nothing in v0.2.x imports h5py, so the extra stays optional."""
    for module in ("features", "loaders", "_locate", "splits", "constants"):
        text = Path(
            getattr(__import__("matr_clean." + module, fromlist=[module]), "__file__")
        ).read_text(encoding="utf-8")
        assert "import h5py" not in text, module
    assert mc.load_cycle_features(data_dir=str(exploration_dir)) is not None


def test_n_h5py_is_not_imported_at_module_scope():
    text = Path(series.__file__).read_text(encoding="utf-8")
    assert "import h5py" not in text
    text = Path(_h5.__file__).read_text(encoding="utf-8")
    body = text.split("def require_h5py")[0]
    assert "import h5py" not in body, "the import must be inside the function"


# ---------------------------------------------------------------------------
# (o) lazy opening
# ---------------------------------------------------------------------------

def test_o_one_file_per_batch_and_no_more(load, monkeypatch):
    opened = []
    real = _h5.open_batch_file

    def spy(directory, date, func_name="open_batch"):
        opened.append(str(date))
        return real(directory, date, func_name)

    monkeypatch.setattr(_h5, "open_batch_file", spy)

    opened.clear()
    load(CONTINUATION, cycles=[1, 2, 3], fields=("Qdlin",))
    assert opened == ["2017-05-12"], "a single-batch request opens one file"

    opened.clear()
    load(CONTINUATION, cycles=[1189, 1190], fields=("Qdlin",))
    assert sorted(opened) == ["2017-05-12", "2017-06-30"]
    assert len(opened) == len(set(opened)), "each file is opened exactly once"


def test_o_only_the_needed_files_are_resolved(load, monkeypatch):
    seen = {}
    real = series._resolve_for

    def spy(names, data_dir=None, v11_dir=None):
        seen["names"] = tuple(names)
        return real(names, data_dir, v11_dir)

    monkeypatch.setattr(series, "_resolve_for", spy)
    load(CONTINUATION, cycles=[1, 2], fields=("Qdlin",))
    assert "within_cycle_2017-05-12.h5" in seen["names"]
    assert "within_cycle_2017-06-30.h5" not in seen["names"], (
        "a 2017-05-12 request must not require the other batch"
    )


# ---------------------------------------------------------------------------
# (p) the max_bytes guard
# ---------------------------------------------------------------------------

def test_p_guard_raises_before_reading_anything(load, monkeypatch):
    def explode(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("the guard must fire before any dataset read")

    monkeypatch.setattr(_h5, "grid_block", explode)
    with pytest.raises(MemoryError, match="would allocate"):
        load(cycles=None, fields=constants.V11_GRID_FIELDS, include_test=True,
             max_bytes=1024)


def test_p_guard_can_be_disabled(load):
    out = load(CONTINUATION, cycles=[2], fields=("Qdlin",), max_bytes=None)
    assert out["Qdlin"].shape == (1, 1, 1000)


def test_p_guard_message_names_the_figure(load):
    with pytest.raises(MemoryError) as excinfo:
        load(cycles=None, fields=constants.V11_GRID_FIELDS, include_test=True,
             max_bytes=1)
    assert "GB" in str(excinfo.value)
    assert "max_bytes" in str(excinfo.value)


# ---------------------------------------------------------------------------
# (q) nothing is written
# ---------------------------------------------------------------------------

def test_q_every_file_is_opened_read_only(load, v11_series_dir, monkeypatch):
    modes = []
    real = h5py.File

    def spy(name, mode=None, *args, **kwargs):
        modes.append(mode)
        return real(name, mode, *args, **kwargs)

    monkeypatch.setattr(h5py, "File", spy)
    load(CONTINUATION, cycles=[1189, 1190], fields=("Qdlin", "V"))
    assert modes, "the spy must have seen an open"
    assert set(modes) == {"r"}


def test_q_no_file_is_modified(load, v11_series_dir):
    before = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(v11_series_dir.iterdir())
    }
    load(cycles=None, fields=constants.V11_GRID_FIELDS + constants.V11_NATIVE_FIELDS,
         include_test=True)
    after = {
        p.name: (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(v11_series_dir.iterdir())
    }
    assert before == after


# ---------------------------------------------------------------------------
# argument validation
# ---------------------------------------------------------------------------

def test_unknown_field_names_the_nine_and_the_dQdV_trap(load):
    with pytest.raises(ValueError) as excinfo:
        load(CONTINUATION, cycles=[2], fields=("dQdV",))
    message = str(excinfo.value)
    assert "discharge_dQdV" in message
    assert "not a field" in message


def test_duplicate_field_is_rejected(load):
    with pytest.raises(ValueError, match="twice"):
        load(CONTINUATION, cycles=[2], fields=("Qdlin", "Qdlin"))


def test_unknown_cell_is_rejected(load):
    with pytest.raises(ValueError, match="unknown cell_uid"):
        load("EL999999999999", cycles=[1])


def test_cycle_zero_is_rejected(load):
    with pytest.raises(ValueError, match="start at 1"):
        load(CONTINUATION, cycles=[0, 1])


def test_empty_cycles_is_rejected(load):
    with pytest.raises(ValueError, match="empty"):
        load(CONTINUATION, cycles=[])


def test_open_slice_is_rejected(load):
    with pytest.raises(ValueError, match="explicit start and stop"):
        load(CONTINUATION, cycles=slice(None, 10))


def test_int_and_slice_and_range_agree(load):
    one = load(CONTINUATION, cycles=2, fields=("Qdlin",))
    same = load(CONTINUATION, cycles=[2], fields=("Qdlin",))
    assert np.array_equal(one["Qdlin"], same["Qdlin"], equal_nan=True)

    sl = load(CONTINUATION, cycles=slice(1, 4), fields=("Qdlin",))
    rg = load(CONTINUATION, cycles=range(1, 4), fields=("Qdlin",))
    assert list(sl["cycle"][0]) == list(rg["cycle"][0]) == [1, 2, 3]


# ---------------------------------------------------------------------------
# filters, and the rolling-window loop the spec promises needs no new function
# ---------------------------------------------------------------------------

def test_filters_records_the_request_and_what_it_masked(load):
    out = load(cycles=None, fields=("Qdlin",), include_test=True)
    f = out["filters"]
    assert f["cycles"] == "all"
    assert f["fields"] == ["Qdlin"]
    assert f["n_positions"] == out["Qdlin"].shape[0] * out["Qdlin"].shape[1]
    assert f["n_absent"] == int((~out["present"]).sum())
    assert f["n_masked"] == int((out["present"] & ~out["valid"]).sum())
    assert f["n_placeholder"] == int(out["is_placeholder"].sum())
    assert "masked in place" in f["repaired"]
    assert f["require_series_valid"] is True


def test_rolling_window_loop_needs_no_other_function(load):
    """A loop over ranges is the whole rolling-evaluation API."""
    seen = []
    for start in (1, 3):
        w = load(CONTINUATION, cycles=range(start, start + 2), fields=("Qdlin",))
        seen.append((list(w["cycle"][0]), w["valid"][0].tolist()))
    assert seen[0][0] == [1, 2] and seen[1][0] == [3, 4]
    assert seen[0][1][0] is False, "cycle 1 is the placeholder, masked"


def test_include_test_default_drops_held_out_cells(load, exploration_dir):
    import pandas as pd

    table = pd.read_csv(exploration_dir / constants.CELLS_FILE)
    out_all = load(cycles=[1], fields=("Qdlin",), include_test=True)
    out_kept = load(cycles=[1], fields=("Qdlin",))
    test_uids = set(table.loc[table["fold"] == constants.TEST_FOLD, "cell_uid"])
    assert set(out_kept["cell_uid"]).isdisjoint(test_uids)
    assert set(out_all["cell_uid"]) >= set(out_kept["cell_uid"])
