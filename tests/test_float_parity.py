"""Floats must come back bit-identical whichever pandas is installed.

The default CSV parser is one unit in the last place away from the correctly
rounded value of the decimal in the file on pandas **2.x and 3.0.x**; pandas 3.1
fixed it, and deprecated the ``float_precision`` argument that worked around it in
the same release. ``matr_clean.loaders`` therefore asks for round-trip parsing below
3.1 and not at or above it, so every supported version is both bit-exact and
warning-free. Python's own ``float()`` is correctly rounded everywhere, which is
what these tests compare against.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

import matr_clean as mc
from matr_clean import constants as C


def test_a_known_value_is_correctly_rounded(exploration_dir):
    cycles = mc.load_cycles(clean=False, include_test=True, data_dir=exploration_dir)
    row = cycles.loc[
        cycles["cell_uid"].eq("EL150800460514") & cycles["cycle"].eq(4.0), "soh"
    ]
    assert len(row) == 1
    loaded = float(row.to_numpy()[0])
    assert loaded.hex() == float("0.9750086363636363").hex()
    assert repr(loaded) == "0.9750086363636363"


@pytest.mark.parametrize("filename", [C.CYCLES_FILE, C.CELLS_FILE])
def test_every_float_matches_python_float_on_the_first_rows(
    exploration_dir, filename
):
    """Parse the file text with Python and compare bit for bit."""
    loader = mc.load_cycles if filename == C.CYCLES_FILE else mc.load_cells
    # both frames must be in the file's own row order, so nothing is filtered
    frame = (
        loader(clean=False, include_test=True, data_dir=exploration_dir)
        if filename == C.CYCLES_FILE
        else loader(include_test=True, data_dir=exploration_dir)
    )
    float_cols = [c for c in frame.columns if frame[c].dtype.kind == "f"]
    assert float_cols

    limit = 3000
    with open(str(exploration_dir / filename), newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader):
            if index >= limit:
                break
            for column in float_cols:
                text = raw[column]
                loaded = frame[column].to_numpy()[index]
                if text == "":
                    assert np.isnan(loaded)
                else:
                    assert float(loaded).hex() == float(text).hex(), (
                        "{0} row {1}: file says {2!r}, pandas loaded {3!r}".format(
                            column, index, text, float(loaded)
                        )
                    )


def test_read_kwargs_suit_the_installed_pandas():
    """The keyword set must match the pandas actually installed.

    This test previously gated on ``major >= 3`` and so asserted the defect it was
    meant to catch: it required pandas 3.0.x to pass *no* keyword, which is exactly
    what left 3.0.x reading one ulp off. The boundary is 3.1, the release that both
    fixed the default parser and deprecated the argument.
    """
    import pandas as pd

    from matr_clean.loaders import _READ_KWARGS, ROUND_TRIP_FIXED_IN, _pandas_version

    if _pandas_version() >= ROUND_TRIP_FIXED_IN:
        assert _READ_KWARGS == {}
    else:
        assert _READ_KWARGS == {"float_precision": "round_trip"}

    # and the keyword set actually delivers parity on this pandas, whichever branch
    # was taken -- the property the gate exists to produce
    import io

    text = "v\n0.9750086363636363\n"
    loaded = pd.read_csv(io.StringIO(text), **_READ_KWARGS)["v"][0]
    assert float(loaded).hex() == float("0.9750086363636363").hex()


def test_no_deprecation_warning_is_raised_when_reading(exploration_dir, recwarn):
    import warnings

    from matr_clean import loaders

    loaders._CACHE.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        warnings.simplefilter("error", FutureWarning)
        assert len(mc.load_cells(data_dir=exploration_dir)) == 135


# ---------------------------------------------------------------------------
# the version gate behind the parity, and the exhaustive check
# ---------------------------------------------------------------------------
# pandas 3.1 fixed the default CSV float parser and deprecated the argument that
# worked around it, in the same release. Below 3.1 the argument is required; at or
# above it, passing it warns. The gate used to be `major >= 3`, which left pandas
# 3.0.x reading one ulp off -- the bug these tests now pin down.

import os
import warnings

import pytest

from matr_clean import loaders


@pytest.mark.parametrize(
    "version,expected",
    [
        ((1, 5), {"float_precision": "round_trip"}),
        ((2, 0), {"float_precision": "round_trip"}),
        ((2, 2), {"float_precision": "round_trip"}),
        ((3, 0), {"float_precision": "round_trip"}),   # the regression: 3.0 needs it
        ((3, 1), {}),                                   # fixed, and deprecated
        ((3, 2), {}),
        ((4, 0), {}),
    ],
)
def test_the_gate_is_at_3_1_not_at_3(version, expected):
    assert loaders._read_csv_kwargs(version=version) == expected


def test_pandas_3_0_is_not_treated_as_fixed():
    """The specific mistake this release corrects, stated as its own test."""
    assert loaders._read_csv_kwargs(version=(3, 0)) == {
        "float_precision": "round_trip"
    }
    assert loaders.ROUND_TRIP_FIXED_IN == (3, 1)


def test_the_version_parser_tolerates_suffixes(monkeypatch):
    import pandas as pd

    for text, expected in [
        ("2.2.3", (2, 2)),
        ("3.0.6", (3, 0)),
        ("3.1.1", (3, 1)),
        ("3.1.0rc0", (3, 1)),
        ("4.0.0.dev0+g1234abc", (4, 0)),
        ("3", (3, 0)),
    ]:
        monkeypatch.setattr(pd, "__version__", text, raising=False)
        assert loaders._pandas_version() == expected, text


def test_an_unparsable_version_errs_towards_passing_the_argument(monkeypatch):
    """The safe direction: a stray warning beats silently corrupting a float."""
    import pandas as pd

    monkeypatch.setattr(pd, "__version__", "not-a-version", raising=False)
    assert loaders._pandas_version() == (0, 0)
    assert loaders._read_csv_kwargs() == {"float_precision": "round_trip"}


def test_reading_a_csv_emits_no_deprecation_or_future_warning(exploration_dir):
    """Whatever this pandas is, the keyword choice must be warning-free.

    ``Pandas4Warning`` subclasses ``DeprecationWarning``, so promoting that category
    to an error is enough to catch the 3.1 deprecation.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        warnings.simplefilter("error", FutureWarning)
        frame = mc.load_cycles(clean=False, include_test=True,
                               data_dir=exploration_dir)
    assert len(frame) == 113559


@pytest.mark.skipif(
    not os.environ.get("MATR_CLEAN_TEST_DATA"),
    reason="set MATR_CLEAN_TEST_DATA to run the exhaustive float-parity check",
)
@pytest.mark.parametrize(
    "filename", [C.CYCLES_FILE, C.CELLS_FILE, C.INVENTORY_FILE]
)
def test_every_float_in_the_whole_file_is_bit_exact(exploration_dir, filename):
    """Every float column, every row -- not the first 3,000.

    The sampled test above runs always and catches a systematic parser change. This
    one reads all 113,559 cycle rows and both cell tables, so a defect confined to
    a handful of values cannot hide in the tail. Gated on the env var because it
    parses every number in the analysis set twice.
    """
    path = exploration_dir / filename
    frame = loaders._read_csv(path)
    float_cols = [c for c in frame.columns if frame[c].dtype.kind == "f"]
    assert float_cols, filename

    checked = 0
    with open(str(path), newline="", encoding="utf-8") as handle:
        for index, raw in enumerate(csv.DictReader(handle)):
            for column in float_cols:
                text = raw[column]
                loaded = frame[column].to_numpy()[index]
                if text == "":
                    assert np.isnan(loaded), (filename, column, index)
                else:
                    assert float(loaded).hex() == float(text).hex(), (
                        "{0} {1} row {2}: file {3!r}, loaded {4!r}".format(
                            filename, column, index, text, float(loaded)
                        )
                    )
                    checked += 1
    assert checked > 0
    if filename == C.CYCLES_FILE:
        assert len(frame) == 113559
        assert checked > 300000, checked
