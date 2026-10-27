"""Shared fixtures.

Every test runs with the download cache pointed at a temporary directory and
``MATR_CLEAN_DATA_DIR`` unset, so no test can read the developer's real cache or
reach the network by accident.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from matr_clean import _locate, constants, loaders


def _find_repo_root() -> Path:
    """The clone this test file lives in, identified by exploration/REPORT.md."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "exploration" / "REPORT.md").is_file():
            return parent
    raise RuntimeError("tests must run from a clone of the repository")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _find_repo_root()


@pytest.fixture(scope="session")
def exploration_dir(repo_root) -> Path:
    return repo_root / "exploration"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Reset every piece of module-level state and isolate the cache."""
    monkeypatch.delenv(constants.DATA_DIR_ENV, raising=False)
    monkeypatch.setenv(constants.CACHE_DIR_ENV, str(tmp_path / "cache"))

    monkeypatch.setattr(_locate, "_SESSION_DIR", None, raising=False)
    monkeypatch.setattr(_locate, "_VERIFIED", set(), raising=False)
    monkeypatch.setattr(loaders, "_CACHE", {}, raising=False)
    yield


@pytest.fixture
def good_copy(tmp_path, exploration_dir) -> Path:
    """A temporary directory holding untouched copies of the three CSVs."""
    target = tmp_path / "good"
    target.mkdir()
    for name in constants.REQUIRED_FILES:
        shutil.copy2(exploration_dir / name, target / name)
    return target


@pytest.fixture
def cells(exploration_dir):
    from matr_clean import load_cells

    return load_cells(data_dir=exploration_dir)


@pytest.fixture
def cycles(exploration_dir):
    """The whole published cycle table, in file order.

    Both of load_cycles' defaults filter, so this fixture turns both off: tests that
    check the published counts or compare against the file text need every row.
    """
    from matr_clean import load_cycles

    return load_cycles(clean=False, include_test=True, data_dir=exploration_dir)
