"""The shape of the API: docstrings carry real counts, nothing is positional."""

from __future__ import annotations

import inspect
import io
import re

import matr_clean as mc
from matr_clean import _docs


PUBLIC = [
    mc.load_cells,
    mc.load_cycles,
    mc.load_trajectories,
    mc.load_labels,
    mc.cv_splits,
]


def test_every_public_function_is_documented():
    for func in PUBLIC + [mc.describe, mc.set_data_dir]:
        assert func.__doc__ and len(func.__doc__.strip()) > 80


def _flat(text):
    """Docstrings are hard-wrapped, so compare against whitespace-normalised text."""
    return re.sub(r"\s+", " ", text or "")


def test_docstring_counts_come_from_the_data(exploration_dir):
    """No count is typed into a docstring: placeholders are filled on first load."""
    mc.load_cells(data_dir=exploration_dir)
    assert _docs.is_filled()
    for func in PUBLIC:
        assert "@@" not in func.__doc__, func.__name__

    # and the filled values are the real ones
    assert "one row per physical cell, 135 rows" in _flat(mc.load_cells.__doc__)
    assert "128 of 135 cells" in _flat(mc.load_labels.__doc__)
    assert "113,559 rows" in _flat(mc.load_cycles.__doc__)
    assert "130 of 135 cells" in _flat(mc.load_trajectories.__doc__)


def test_no_count_is_a_literal_in_the_source():
    """The counts above are substituted at run time, not typed into the source."""
    import pathlib

    package = pathlib.Path(mc.__file__).parent
    for name in ("loaders.py", "splits.py"):
        source = (package / name).read_text()
        in_docstrings = re.findall(r"@@\w+@@", source)
        assert in_docstrings, "{0} should document its counts with placeholders".format(name)
        for literal in ("135 rows", "128 of 135", "113,559", "130 of 135", "123 cells"):
            assert literal not in source, "{0} hard-codes {1!r}".format(name, literal)


def test_docstrings_name_the_default_each_filter_applies(exploration_dir):
    mc.load_cells(data_dir=exploration_dir)
    assert "27 held-out test cells" in _flat(mc.load_cells.__doc__)
    doc = _flat(mc.load_cycles.__doc__)
    assert "90,314 rows" in doc        # the default: clean, no held-out cells
    assert "113,394" in doc            # clean but with them
    assert "165 rows it removes" in doc
    assert "23,100 cycles" in doc      # what include_test=False drops
    splits_doc = _flat(mc.cv_splits.__doc__)
    assert "5 splits" in splits_doc
    assert "60 splits" in splits_doc
    assert "the 27 cells with ``fold == -1``" in splits_doc


def test_cv_splits_docstring_states_the_fold_limitation():
    doc = _flat(mc.cv_splits.__doc__)
    assert (
        "only tests new cells from batches and policies the model has already seen"
        in doc
    )


def test_signatures_are_keyword_friendly():
    expected = {
        "load_cells": ["include_test", "data_dir"],
        "load_cycles": ["clean", "include_test", "data_dir"],
        "load_labels": ["include_test", "data_dir"],
        "cv_splits": ["kind", "include_test", "data_dir"],
    }
    for name, params in expected.items():
        func = getattr(mc, name)
        assert list(inspect.signature(func).parameters) == params


def test_defaults_are_as_documented():
    sig = inspect.signature(mc.load_cycles).parameters
    assert sig["clean"].default is True
    # every loader that returns cycles, and every split, protects the held-out cells
    assert sig["include_test"].default is False
    assert inspect.signature(mc.load_labels).parameters["include_test"].default is False
    assert (
        inspect.signature(mc.load_trajectories).parameters["include_test"].default
        is False
    )
    assert inspect.signature(mc.cv_splits).parameters["include_test"].default is False
    # load_cells is the exception: an inventory view, one row per cell, no cycles
    assert inspect.signature(mc.load_cells).parameters["include_test"].default is True


def test_describe_prints_the_counts(exploration_dir):
    buffer = io.StringIO()
    numbers = mc.describe(data_dir=exploration_dir, file=buffer)
    text = buffer.getvalue()
    assert "135 physical cells" in text
    assert "113,559 cycles" in text
    assert "What each default excludes" in text
    assert "voltage-domain features" in text
    assert numbers["n_cells"] == 135
    # nothing printed contradicts the counts it returns
    assert "{0:,}".format(numbers["n_cycles_clean"]) in text


def test_no_positional_cell_addressing_in_the_source():
    """Cells are addressed by cell_uid or barcode, never by row position."""
    import pathlib

    package = pathlib.Path(mc.__file__).parent
    offenders = []
    for path in sorted(package.glob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"\.iloc\b|\.iat\b|\.ix\b", code):
                offenders.append("{0}:{1}: {2}".format(path.name, number, line.strip()))
    assert offenders == [], "positional indexing found:\n" + "\n".join(offenders)


def test_version_and_exports():
    assert re.match(r"^\d+\.\d+\.\d+$", mc.__version__)
    for name in mc.__all__:
        assert hasattr(mc, name), name
