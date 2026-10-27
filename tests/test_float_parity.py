"""Floats must come back bit-identical whichever pandas is installed.

pandas 2's default CSV parser can be one unit in the last place away from the
correctly rounded value of the decimal in the file; pandas 3's default is correct.
``matr_clean.loaders`` asks pandas 2 for round-trip parsing so both agree. Python's
own ``float()`` is correctly rounded on every version, which is what these tests
compare against.
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
    import pandas as pd

    from matr_clean.loaders import _READ_KWARGS

    major = int(pd.__version__.split(".")[0])
    if major >= 3:
        assert _READ_KWARGS == {}
    else:
        assert _READ_KWARGS == {"float_precision": "round_trip"}


def test_no_deprecation_warning_is_raised_when_reading(exploration_dir, recwarn):
    import warnings

    from matr_clean import loaders

    loaders._CACHE.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        warnings.simplefilter("error", FutureWarning)
        assert len(mc.load_cells(data_dir=exploration_dir)) == 135
