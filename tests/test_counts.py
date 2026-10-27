"""The counts the loader returns, and that they match exploration/REPORT.md."""

from __future__ import annotations

import re

import pytest

import matr_clean as mc
from matr_clean import constants as C


def test_cell_table_is_135_rows(cells):
    assert len(cells) == 135
    assert cells["cell_uid"].nunique() == 135
    assert cells["barcode"].nunique() == 135
    # cell_uid is the barcode, which is what makes grouping by either equivalent.
    assert (cells["cell_uid"] == cells["barcode"]).all()


def test_128_cells_are_labelled(cells):
    assert int(cells["has_eol_label"].sum()) == 128
    assert int((~cells["has_eol_label"]).sum()) == 7
    # the 7 unlabelled cells are exactly the censored ones (decision D4)
    assert (cells["censored"] == ~cells["has_eol_label"]).all()


def test_labels_loader_returns_the_labelled_cells(exploration_dir):
    allcells = mc.load_labels(include_test=True, data_dir=exploration_dir)
    assert len(allcells) == 128
    assert allcells["has_eol_label"].all()
    assert allcells["eol_cycle_80pct_soh"].notna().all()
    assert set(allcells["eol_basis"].unique()) == {
        "strict_crossing_below_0.88Ah",
        "test_terminated_at_criterion",
    }
    assert (allcells["cycle_life_cycles"] == allcells["eol_cycle_80pct_soh"]).all()
    # the default protects the held-out cells
    default = mc.load_labels(data_dir=exploration_dir)
    assert len(default) == 102
    assert (default["fold"] != C.TEST_FOLD).all()


def test_trajectory_counts(exploration_dir):
    traj = mc.load_trajectories(include_test=True, clean=False, data_dir=exploration_dir)
    assert len(traj.cells) == 130
    assert traj.cells["use_for_trajectory"].all()
    assert not traj.cells["is_continuation"].any()

    labelled = mc.load_trajectories(
        include_test=True, labelled_only=True, data_dir=exploration_dir
    )
    assert len(labelled.cells) == 123

    default = mc.load_trajectories(data_dir=exploration_dir)
    assert len(default.cells) == 104
    assert (default.cells["fold"] != C.TEST_FOLD).all()
    # the cycles that come back belong only to the cells that came back
    assert set(default.cycles["cell_uid"]) == set(default.cells["cell_uid"])


def test_other_cell_categories(cells):
    assert int(cells["is_continuation"].sum()) == 5
    assert int(cells["in_paper_124"].sum()) == 124
    assert int((cells["fold"] == C.TEST_FOLD).sum()) == 27
    assert cells["batch_date"].nunique() == 3


def test_cycle_table_row_count(cycles):
    assert len(cycles) == 113559
    assert cycles["cell_uid"].nunique() == 135


def test_clean_filter_is_the_documented_conjunction(cycles):
    """is_clean_cycle == measured AND not (artifact OR restart OR junction)."""
    conjunction = cycles[C.MEASURED_FLAG]
    for flag in C.REJECT_FLAGS:
        conjunction = conjunction & ~cycles[flag]
    assert (conjunction == cycles[C.CLEAN_FLAG]).all()
    assert int(cycles[C.CLEAN_FLAG].sum()) == 113394
    assert int((~cycles[C.CLEAN_FLAG]).sum()) == 165


def test_clean_default_keeps_only_clean_rows(exploration_dir):
    """Both defaults filter: clean rows only, and no held-out test cells."""
    kept = mc.load_cycles(data_dir=exploration_dir)
    assert len(kept) == 90314
    assert kept[C.CLEAN_FLAG].all()
    assert not kept["cell_uid"].isin(_test_uids(exploration_dir)).any()

    clean_everywhere = mc.load_cycles(include_test=True, data_dir=exploration_dir)
    assert len(clean_everywhere) == 113394
    assert clean_everywhere[C.CLEAN_FLAG].all()

    all_cells_no_clean = mc.load_cycles(
        clean=False, include_test=True, data_dir=exploration_dir
    )
    assert len(all_cells_no_clean) == 113559

    no_test_no_clean = mc.load_cycles(clean=False, data_dir=exploration_dir)
    assert len(no_test_no_clean) == 90459


def _test_uids(exploration_dir):
    cells = mc.load_cells(data_dir=exploration_dir)
    return set(cells.loc[cells["fold"] == C.TEST_FOLD, "cell_uid"])


def test_counts_dict_is_self_consistent(exploration_dir):
    n = mc.counts(data_dir=exploration_dir)
    assert n["n_cells"] == n["n_labelled"] + n["n_unlabelled"]
    assert n["n_cells"] == n["n_cells_excl_test"] + n["n_test_cells"]
    assert n["n_cycles"] == n["n_cycles_clean"] + n["n_cycles_flagged"]
    assert n["n_cycles"] == n["n_cycles_excl_test"] + n["n_test_cycles"]
    assert n["n_traj_labelled"] <= n["n_traj"] <= n["n_cells"]


# ---------------------------------------------------------------------------
# cross-check against the published report
# ---------------------------------------------------------------------------

def _report_section_7(repo_root) -> str:
    text = (repo_root / "exploration" / "REPORT.md").read_text(encoding="utf-8")
    start = text.index("## 7. The resulting analysis set")
    end = text.index("## 8.", start)
    return text[start:end]


def _table_numbers(section: str):
    found = {}
    for line in section.splitlines():
        match = re.match(r"^\|\s*(.+?)\s*\|\s*\**([\d,]+)\**\s*\|\s*$", line)
        if match:
            label = match.group(1).strip().strip("`").lower()
            found[label] = int(match.group(2).replace(",", ""))
    return found


def test_counts_match_report_section_7(repo_root, exploration_dir):
    section = _report_section_7(repo_root)
    n = mc.counts(data_dir=exploration_dir)

    # the fenced block at the top of the section
    block = re.search(r"analysis_set_cells\.csv\s+([\d,]+) cells", section)
    assert block is not None
    assert int(block.group(1).replace(",", "")) == n["n_cells"]
    block = re.search(r"analysis_set_cycles\.csv\s+([\d,]+) cycles", section)
    assert block is not None
    assert int(block.group(1).replace(",", "")) == n["n_cycles"]

    table = _table_numbers(section)
    assert table["physical cells"] == n["n_cells"]
    assert table["with an 80% soh label"] == n["n_labelled"]
    assert table["censored, no label"] == n["n_unlabelled"]
    assert table["continuations, off by default"] == n["n_continuation"]
    assert table["in_paper_124"] == n["n_in_paper"]
    # REPORT.md section 7 calls this 123 == use_for_trajectory & has_eol_label.
    # See test_definitions.py for the reconciliation.
    assert table["default trajectory training set"] == n["n_traj_labelled"]


def test_report_validation_claim_43_strict_crossings(repo_root, cells):
    text = (repo_root / "exploration" / "REPORT.md").read_text(encoding="utf-8")
    assert "Exactly 43 **measured** cycles sit below 0.88 Ah" in text
    assert int((cells["eol_basis"] == "strict_crossing_below_0.88Ah").sum()) == 43
    assert int((cells["eol_basis"] == "test_terminated_at_criterion").sum()) == 85


def test_row_counts_reconcile_with_n_cycles_kept(cells, cycles):
    assert int(cells["n_cycles_kept"].sum()) == len(cycles)
