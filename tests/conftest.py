"""Shared fixtures.

Every test runs with the download cache pointed at a temporary directory and
``MATR_CLEAN_DATA_DIR`` unset, so no test can read the developer's real cache or
reach the network by accident. Retry backoff is stubbed out too, so a test that
exercises the retry path proves the waits happen without spending them; a test that
cares about their length patches ``_locate._sleep`` with its own recorder.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from matr_clean import _locate, constants, features, loaders

#: Set this to a directory holding the published within_cycle_* files to run the
#: integration tests against the real 114,738-row index. Unset, they skip.
REAL_DATA_ENV = "MATR_CLEAN_TEST_DATA"


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
    monkeypatch.setattr(_locate, "_V11_VERIFIED", set(), raising=False)
    monkeypatch.setattr(loaders, "_CACHE", {}, raising=False)
    monkeypatch.setattr(features, "_V11_CACHE", {}, raising=False)
    monkeypatch.setattr(_locate, "_sleep", lambda seconds: None, raising=False)
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


# ---------------------------------------------------------------------------
# v1.1 fixtures
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@pytest.fixture
def v11_dir(tmp_path, monkeypatch) -> Path:
    """A directory holding the committed v1.1 fixture, with hashes repointed.

    The fixture is a 223-row subset of the real index (see
    ``tests/fixtures/make_v11_fixture.py``), so it has the real schema and the real
    pathological rows but not the real SHA-256. The constants are monkeypatched to
    the fixture's own hashes, which keeps the whole resolve-and-verify path under
    test rather than bypassed: a corrupted fixture still raises IntegrityError.
    """
    source = Path(__file__).resolve().parent / "fixtures"
    target = tmp_path / "v11"
    target.mkdir()
    hashes = {}
    sizes = {}
    for name in constants.V11_REQUIRED_FILES:
        shutil.copy2(source / name, target / name)
        hashes[name] = _sha256(target / name)
        sizes[name] = (target / name).stat().st_size

    monkeypatch.setitem(constants.V11_SHA256, constants.V11_INDEX_FILE,
                        hashes[constants.V11_INDEX_FILE])
    monkeypatch.setitem(constants.V11_SHA256, constants.V11_CELLS_FILE,
                        hashes[constants.V11_CELLS_FILE])
    monkeypatch.setitem(constants.V11_SIZE_BYTES, constants.V11_INDEX_FILE,
                        sizes[constants.V11_INDEX_FILE])
    monkeypatch.setitem(constants.V11_SIZE_BYTES, constants.V11_CELLS_FILE,
                        sizes[constants.V11_CELLS_FILE])
    return target


@pytest.fixture
def fixture_cells() -> tuple:
    """The eight cell_uids the fixture covers."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
    try:
        from make_v11_fixture import CELLS
    finally:
        sys.path.pop(0)
    return CELLS


@pytest.fixture(scope="session")
def real_v11_dir():
    """The published v1.1 files, or skip. Opened read-only, never written."""
    raw = os.environ.get(REAL_DATA_ENV)
    if not raw:
        pytest.skip(
            "set {0} to a directory holding the published within_cycle_* files "
            "to run the integration tests".format(REAL_DATA_ENV)
        )
    directory = Path(raw).expanduser().resolve()
    missing = [
        name for name in constants.V11_REQUIRED_FILES
        if not (directory / name).is_file()
    ]
    if missing:
        pytest.skip("{0} does not hold {1}".format(directory, ", ".join(missing)))
    return directory
