"""What "the default trajectory set" actually is.

REPORT.md section 7 used to call 123 cells the default trajectory training set while
comparison_external_repos.md section 4.2 called 130 cells the default trajectory set,
"123 of which are labelled". Both numbers describe this data correctly -- they are two
different sets, and the phrase was doing double duty. Both documents now name the
predicate behind each count, and these tests hold them to it: 130 is
``use_for_trajectory``, 123 is ``use_for_trajectory & has_eol_label``.
"""

from __future__ import annotations

import matr_clean as mc


def test_use_for_trajectory_is_130_cells(cells):
    assert int(cells["use_for_trajectory"].sum()) == 130
    # it is exactly "not a continuation" (decision D3), nothing else
    assert (cells["use_for_trajectory"] == ~cells["is_continuation"]).all()


def test_use_for_trajectory_and_labelled_is_123_cells(cells):
    assert int((cells["use_for_trajectory"] & cells["has_eol_label"]).sum()) == 123
    # the 7 difference is the censored cells, 5 of which... no: all 7 are
    # non-continuations, so 130 - 7 = 123
    assert int((cells["use_for_trajectory"] & ~cells["has_eol_label"]).sum()) == 7
    assert int((cells["is_continuation"] & ~cells["has_eol_label"]).sum()) == 0


def test_the_loader_offers_both_and_names_them(exploration_dir):
    traj = mc.load_trajectories(include_test=True, data_dir=exploration_dir)
    assert len(traj.cells) == 130
    labelled = mc.load_trajectories(
        include_test=True, labelled_only=True, data_dir=exploration_dir
    )
    assert len(labelled.cells) == 123
    doc = mc.load_trajectories.__doc__
    assert "123" in doc and "130" in doc
    assert "use_for_trajectory" in doc


def test_both_published_statements_are_true_of_the_data(repo_root, cells):
    """Neither document is wrong about the data; only the phrase is overloaded."""
    report = (repo_root / "exploration" / "REPORT.md").read_text(encoding="utf-8")
    comparison = (
        repo_root / "exploration" / "comparison_external_repos.md"
    ).read_text(encoding="utf-8")

    assert (
        "default trajectory set, labelled (`use_for_trajectory & has_eol_label`) "
        "| **123**" in report
    )
    assert "default trajectory set (`use_for_trajectory`) | 130 |" in report
    assert (
        "this repo's default trajectory set (`use_for_trajectory`) | **130** "
        "(123 of which are labelled)" in comparison
    )

    n_traj = int(cells["use_for_trajectory"].sum())
    n_traj_labelled = int((cells["use_for_trajectory"] & cells["has_eol_label"]).sum())
    assert (n_traj, n_traj_labelled) == (130, 123)
