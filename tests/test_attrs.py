"""Every returned frame records the filters that produced it."""

from __future__ import annotations

import matr_clean as mc
from matr_clean import constants as C

REQUIRED_KEYS = {
    "function",
    "applied",
    "excluded",
    "n_rows_in",
    "n_rows_out",
    "data_tag",
    "data_dir",
    "data_source",
}


def _check(frame, function, applied):
    filters = frame.attrs["filters"]
    assert REQUIRED_KEYS <= set(filters)
    assert filters["function"] == function
    assert filters["applied"] == applied
    assert filters["n_rows_out"] == len(frame)
    assert filters["data_tag"] == C.DATA_TAG
    return filters


def test_load_cells_attrs(exploration_dir):
    frame = mc.load_cells(data_dir=exploration_dir)
    filters = _check(frame, "load_cells", {"include_test": True})
    assert filters["excluded"] == []
    assert filters["n_rows_in"] == 135

    frame = mc.load_cells(include_test=False, data_dir=exploration_dir)
    filters = _check(frame, "load_cells", {"include_test": False})
    assert any("27 cells" in line for line in filters["excluded"])


def test_load_cycles_attrs(exploration_dir):
    frame = mc.load_cycles(data_dir=exploration_dir)
    filters = _check(frame, "load_cycles", {"clean": True, "include_test": False})
    assert filters["n_rows_in"] == 113559
    assert any("is_clean_cycle" in line for line in filters["excluded"])
    assert any("fold == -1" in line for line in filters["excluded"])

    frame = mc.load_cycles(clean=False, include_test=False, data_dir=exploration_dir)
    filters = _check(frame, "load_cycles", {"clean": False, "include_test": False})
    assert any("fold == -1" in line for line in filters["excluded"])
    assert not any("is_clean_cycle" in line for line in filters["excluded"])

    frame = mc.load_cycles(clean=True, include_test=True, data_dir=exploration_dir)
    filters = _check(frame, "load_cycles", {"clean": True, "include_test": True})
    assert not any("fold == -1" in line for line in filters["excluded"])


def test_excluded_counts_add_up(exploration_dir):
    """The numbers quoted in `excluded` account for every row that was removed."""
    frame = mc.load_cycles(clean=True, include_test=False, data_dir=exploration_dir)
    filters = frame.attrs["filters"]
    import re

    removed = sum(
        int(match.group(1).replace(",", ""))
        for line in filters["excluded"]
        for match in [re.search(r"([\d,]+) rows", line)]
        if match
    )
    assert filters["n_rows_in"] - removed == filters["n_rows_out"]


def test_load_trajectories_attrs(exploration_dir):
    traj = mc.load_trajectories(data_dir=exploration_dir)
    applied = {
        "clean": True,
        "include_test": False,
        "labelled_only": False,
        "use_for_trajectory": True,
    }
    _check(traj.cells, "load_trajectories.cells", applied)
    _check(traj.cycles, "load_trajectories.cycles", applied)
    assert any(
        "use_for_trajectory" in line for line in traj.cells.attrs["filters"]["excluded"]
    )


def test_load_labels_attrs(exploration_dir):
    frame = mc.load_labels(data_dir=exploration_dir)
    filters = _check(frame, "load_labels", {"include_test": False})
    assert any("has_eol_label" in line for line in filters["excluded"])
    assert any("fold == -1" in line for line in filters["excluded"])


def test_attrs_survive_a_copy(exploration_dir):
    frame = mc.load_cells(data_dir=exploration_dir)
    assert frame.copy().attrs["filters"] == frame.attrs["filters"]


def test_mutating_a_returned_frame_does_not_affect_the_next_call(exploration_dir):
    first = mc.load_cells(data_dir=exploration_dir)
    first.loc[:, "has_eol_label"] = False
    second = mc.load_cells(data_dir=exploration_dir)
    assert int(second["has_eol_label"].sum()) == 128
