"""Shared fixtures.

Every test runs with the download cache pointed at a temporary directory,
``MATR_CLEAN_DATA_DIR`` unset and ``urlopen`` replaced by one that raises, so no
test can read the developer's real cache or reach the network by accident. Retry
backoff is stubbed out too, so a test that exercises the retry path proves the waits
happen without spending them; a test that cares about their length patches
``_locate._sleep`` with its own recorder.
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


@pytest.fixture(autouse=True)
def no_accidental_network(request, monkeypatch):
    """Nothing in this suite may open a URL unless it says so.

    Until the v1.1 record was published, ``V11_ZENODO_BASE is None`` was what kept
    the suite offline: there was no URL to fetch. Step 5 can now really download
    72.8 MB, so this file's promise has to be enforced rather than implied.

    A test that wants the download path replaces ``urlopen`` with its own stub,
    which overrides this one. A test that genuinely wants the published record
    carries ``@pytest.mark.network`` and is skipped unless opted into.
    """
    if request.node.get_closest_marker("network"):
        return

    import urllib.request

    def refuse(url, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError(
            "this test opened {0!r}. Install a urlopen stub, or mark it "
            "@pytest.mark.network if it is meant to use the real record.".format(url)
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture
def record_blanked(monkeypatch):
    """Put the Zenodo constants back to their pre-publication ``None``.

    The published record makes the no-record path unreachable in a normal install,
    and it is still the path a fork or a mid-edit revision takes, so it stays
    tested. Blanking the constants is how: the behaviour is a function of them, by
    design, which is the whole point of keeping them in one module.
    """
    for name in ("V11_ZENODO_DOI", "V11_ZENODO_CONCEPT_DOI",
                 "V11_ZENODO_RECORD_ID", "V11_ZENODO_BASE",
                 "V11_ZENODO_RECORD_URL", "V11_DATA_TAG"):
        monkeypatch.setattr(constants, name, None)
    assert constants.v11_is_published() is False


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
def no_local_v11(monkeypatch):
    """Hide any v1.1 data that happens to be in this clone.

    Step 4 of the lookup order walks up from the installed package and from the
    working directory looking for ``exploration/extract_out/``. That is exactly
    what it should do -- and it means a clone with the v1.1 files in place, which
    is the layout USAGE.md recommends, resolves successfully where a bare checkout
    raises.

    A test that wants the no-data-anywhere path therefore has to say so, the same
    way ``isolated_state`` already redirects the cache and unsets the env var.
    Without this the two "unpublished" tests pass in a fresh checkout and fail on
    a working machine, which is the wrong way round.
    """
    monkeypatch.setattr(_locate, "_repo_v11_dirs", lambda names: [], raising=False)


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
def v11_series_dir(tmp_path, monkeypatch) -> Path:
    """The committed within-cycle **series** fixture, with hashes repointed.

    ``tests/fixtures/series/`` holds two tiny HDF5 files and a 12-row index that
    matches them (see ``tests/fixtures/make_v11_series_fixture.py``). Copying it to
    a temporary directory and monkeypatching the constants to the fixture's own
    SHA-256 keeps the whole resolve-and-verify path under test rather than bypassed:
    a corrupted fixture still raises IntegrityError, and no 2.20 GB of real data is
    needed to run any of it.

    Pair it with ``exploration_dir`` as ``data_dir=``: the v1.0 CSVs are hash-pinned
    and committed, so the join that supplies ``is_clean_cycle`` is the real one.
    """
    source = Path(__file__).resolve().parent / "fixtures" / "series"
    target = tmp_path / "v11series"
    target.mkdir()
    names = list(constants.V11_REQUIRED_FILES) + [
        name for name in sorted(constants.V11_H5_FILES.values())
        if (source / name).is_file()
    ]
    for name in names:
        shutil.copy2(source / name, target / name)
        monkeypatch.setitem(constants.V11_SHA256, name, _sha256(target / name))
        monkeypatch.setitem(
            constants.V11_SIZE_BYTES, name, (target / name).stat().st_size
        )
    return target


@pytest.fixture
def series_fixture_rows():
    """The ``(cell_uid, cycle)`` rows the series fixture covers, and why."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
    try:
        from make_v11_series_fixture import ROWS, NATIVE_SAMPLES
    finally:
        sys.path.pop(0)
    return {"rows": ROWS, "native_samples": NATIVE_SAMPLES}


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
