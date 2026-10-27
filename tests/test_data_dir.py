"""The lookup order, the integrity check, and the errors they raise."""

from __future__ import annotations

import shutil
import urllib.error
from pathlib import Path

import pytest

import matr_clean as mc
from matr_clean import _locate, constants as C


def _listing(directory: Path):
    """Name, size and mtime of every entry, to prove nothing was written."""
    return sorted(
        (p.name, p.stat().st_size, p.stat().st_mtime_ns)
        for p in directory.iterdir()
    )


# ---------------------------------------------------------------------------
# a good directory
# ---------------------------------------------------------------------------

def test_explicit_data_dir_loads(good_copy):
    cells = mc.load_cells(data_dir=good_copy)
    assert len(cells) == 135
    assert cells.attrs["filters"]["data_dir"] == str(good_copy.resolve())


def test_loading_never_writes_into_a_user_directory(good_copy):
    before = _listing(good_copy)
    mc.load_cells(data_dir=good_copy)
    mc.load_cycles(data_dir=good_copy)
    mc.load_trajectories(data_dir=good_copy)
    list(mc.cv_splits("fold", data_dir=good_copy))
    assert _listing(good_copy) == before


def test_set_data_dir_is_used_for_later_calls(good_copy):
    resolved = mc.set_data_dir(good_copy)
    assert resolved == good_copy.resolve()
    assert mc.get_data_dir() == good_copy.resolve()
    assert len(mc.load_cells()) == 135


def test_env_var_is_used(good_copy, monkeypatch):
    monkeypatch.setenv(C.DATA_DIR_ENV, str(good_copy))
    assert len(mc.load_cells()) == 135
    assert mc.load_cells().attrs["filters"]["data_dir"] == str(good_copy.resolve())


def test_explicit_argument_wins_over_the_session_directory(good_copy, exploration_dir):
    mc.set_data_dir(exploration_dir)
    cells = mc.load_cells(data_dir=good_copy)
    assert cells.attrs["filters"]["data_dir"] == str(good_copy.resolve())


def test_session_directory_wins_over_the_env_var(good_copy, exploration_dir, monkeypatch):
    monkeypatch.setenv(C.DATA_DIR_ENV, str(exploration_dir))
    mc.set_data_dir(good_copy)
    assert mc.load_cells().attrs["filters"]["data_dir"] == str(good_copy.resolve())


def test_clone_is_found_with_nothing_configured(exploration_dir):
    """Step 4: running from a clone needs no configuration at all."""
    cells = mc.load_cells()
    assert len(cells) == 135
    assert Path(cells.attrs["filters"]["data_dir"]) == exploration_dir.resolve()
    assert "exploration" in cells.attrs["filters"]["data_source"]


# ---------------------------------------------------------------------------
# a bad directory
# ---------------------------------------------------------------------------

def test_one_changed_byte_is_rejected(good_copy):
    target = good_copy / C.CELLS_FILE
    data = bytearray(target.read_bytes())
    original_size = len(data)
    # flip one byte inside a numeric field, leaving the file the same length
    data[5000] = data[5000] ^ 0x01
    target.write_bytes(bytes(data))
    assert target.stat().st_size == original_size

    with pytest.raises(mc.IntegrityError) as excinfo:
        mc.load_cells(data_dir=good_copy)

    message = str(excinfo.value)
    assert C.CELLS_FILE in message
    assert C.SHA256[C.CELLS_FILE] in message          # expected
    assert "actual:" in message
    # the actual hash is quoted, and it is not the expected one
    actual = [
        line.split("actual:")[1].strip()
        for line in message.splitlines()
        if "actual:" in line
    ][0]
    assert len(actual) == 64 and actual != C.SHA256[C.CELLS_FILE]


def test_a_bad_directory_never_falls_back_to_the_clone(good_copy, exploration_dir):
    """The repository's own exploration/ folder would load fine; it must not be used."""
    (good_copy / C.CYCLES_FILE).write_bytes(b"not,a,cycle,table\n")
    with pytest.raises(mc.IntegrityError):
        mc.load_cells(data_dir=good_copy)
    with pytest.raises(mc.IntegrityError):
        mc.load_cycles(data_dir=good_copy)


def test_a_bad_file_is_not_deleted_from_a_user_directory(good_copy):
    target = good_copy / C.CELLS_FILE
    data = bytearray(target.read_bytes())
    data[5000] = data[5000] ^ 0x01
    target.write_bytes(bytes(data))
    with pytest.raises(mc.IntegrityError):
        mc.load_cells(data_dir=good_copy)
    assert target.is_file(), "the loader must not delete a user's file"


def test_misnamed_files_are_named_in_the_error(tmp_path, exploration_dir):
    directory = tmp_path / "downloads"
    directory.mkdir()
    shutil.copy2(exploration_dir / C.CELLS_FILE, directory / C.CELLS_FILE)
    shutil.copy2(exploration_dir / C.INVENTORY_FILE, directory / C.INVENTORY_FILE)
    # the shape a second browser download takes
    shutil.copy2(exploration_dir / C.CYCLES_FILE, directory / "analysis_set_cycles (1).csv")

    with pytest.raises(mc.DataDirError) as excinfo:
        mc.load_cycles(data_dir=directory)

    message = str(excinfo.value)
    assert C.CYCLES_FILE in message
    assert "analysis_set_cycles (1).csv" in message
    assert "rename" in message.lower()


def test_an_empty_directory_lists_what_is_required(tmp_path):
    directory = tmp_path / "empty"
    directory.mkdir()
    with pytest.raises(mc.DataDirError) as excinfo:
        mc.load_cells(data_dir=directory)
    message = str(excinfo.value)
    for name in C.REQUIRED_FILES:
        assert name in message


def test_set_data_dir_rejects_a_bad_directory_and_keeps_the_old_one(
    good_copy, tmp_path
):
    mc.set_data_dir(good_copy)
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(mc.DataDirError):
        mc.set_data_dir(empty)
    assert mc.get_data_dir() == good_copy.resolve()


# ---------------------------------------------------------------------------
# verification happens once per process
# ---------------------------------------------------------------------------

def test_verification_is_once_per_process(good_copy):
    assert len(mc.load_cells(data_dir=good_copy)) == 135
    # corrupt the file afterwards: the directory is already verified, and the tables
    # are already in memory, so no second hash is computed
    (good_copy / C.CELLS_FILE).write_bytes(b"broken\n")
    assert len(mc.load_cells(data_dir=good_copy)) == 135
    assert str(good_copy.resolve()) in _locate._VERIFIED


# ---------------------------------------------------------------------------
# the cache and the download (no network in these tests)
# ---------------------------------------------------------------------------

def test_cache_is_used_without_downloading(good_copy, monkeypatch):
    cache = C.cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    for name in C.REQUIRED_FILES:
        shutil.copy2(good_copy / name, cache / name)

    monkeypatch.setattr(_locate, "_repo_exploration_dirs", lambda: [])

    def explode(*args, **kwargs):
        raise AssertionError("the cache was populated; nothing should be downloaded")

    monkeypatch.setattr(_locate.urllib.request, "urlopen", explode)
    cells = mc.load_cells()
    assert len(cells) == 135
    assert Path(cells.attrs["filters"]["data_dir"]) == cache.resolve()


def test_download_populates_the_cache(good_copy, monkeypatch):
    """Step 5, with the network stubbed out by a local file."""
    monkeypatch.setattr(_locate, "_repo_exploration_dirs", lambda: [])
    wanted = []

    class FakeResponse:
        def __init__(self, path):
            self._handle = open(str(path), "rb")

        def read(self, *args):
            return self._handle.read(*args)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()
            return False

    def fake_urlopen(url, timeout=None):
        name = url.rsplit("/", 1)[-1]
        wanted.append(url)
        return FakeResponse(good_copy / name)

    monkeypatch.setattr(_locate.urllib.request, "urlopen", fake_urlopen)

    cells = mc.load_cells()
    assert len(cells) == 135
    cache = C.cache_dir()
    assert Path(cells.attrs["filters"]["data_dir"]) == cache.resolve()
    assert sorted(p.name for p in cache.iterdir()) == sorted(C.REQUIRED_FILES)
    assert all("/v1.0/" in url for url in wanted)
    assert len(wanted) == 3


def test_a_corrupt_download_is_deleted_and_raises(good_copy, monkeypatch, tmp_path):
    monkeypatch.setattr(_locate, "_repo_exploration_dirs", lambda: [])

    truncated = tmp_path / "truncated.csv"
    truncated.write_bytes(b"cell_uid,barcode\nx,y\n")

    class FakeResponse:
        def __init__(self, path):
            self._handle = open(str(path), "rb")

        def read(self, *args):
            return self._handle.read(*args)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()
            return False

    def fake_urlopen(url, timeout=None):
        name = url.rsplit("/", 1)[-1]
        if name == C.CYCLES_FILE:
            return FakeResponse(truncated)
        return FakeResponse(good_copy / name)

    monkeypatch.setattr(_locate.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(mc.IntegrityError) as excinfo:
        mc.load_cells()
    assert C.CYCLES_FILE in str(excinfo.value)
    # the bad download is gone, so the next attempt starts clean
    assert not (C.cache_dir() / C.CYCLES_FILE).exists()


def test_offline_error_lists_the_urls_and_the_way_out(monkeypatch):
    monkeypatch.setattr(_locate, "_repo_exploration_dirs", lambda: [])

    def offline(url, timeout=None):
        raise urllib.error.URLError("Network is unreachable")

    monkeypatch.setattr(_locate.urllib.request, "urlopen", offline)

    with pytest.raises(mc.DownloadError) as excinfo:
        mc.load_cells()
    message = str(excinfo.value)
    for name in C.REQUIRED_FILES:
        assert C.url_for(name) in message
    assert C.DATA_DIR_ENV in message
    assert "set_data_dir" in message
    # no half-written file is left behind
    cache = C.cache_dir()
    if cache.exists():
        assert not any(p.suffix == ".part" for p in cache.iterdir())


def test_no_download_is_left_partially_written(monkeypatch):
    monkeypatch.setattr(_locate, "_repo_exploration_dirs", lambda: [])

    class HalfResponse:
        def read(self, *args):
            raise urllib.error.URLError("connection reset")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        _locate.urllib.request, "urlopen", lambda url, timeout=None: HalfResponse()
    )
    with pytest.raises(mc.DownloadError):
        mc.load_cells()
    cache = C.cache_dir()
    if cache.exists():
        assert list(cache.iterdir()) == []


# ---------------------------------------------------------------------------
# the Google Drive shape: a mounted, read-only folder with a space in the path
# ---------------------------------------------------------------------------

def test_a_read_only_folder_with_a_space_in_its_path_loads(tmp_path, exploration_dir):
    """What a mounted Drive folder looks like: /content/drive/My Drive/..."""
    directory = tmp_path / "drive" / "My Drive" / "matr_clean_data"
    directory.mkdir(parents=True)
    for name in C.REQUIRED_FILES:
        shutil.copy2(exploration_dir / name, directory / name)
    directory.chmod(0o555)
    try:
        mc.set_data_dir(directory)
        assert len(mc.load_cells()) == 135
        assert len(mc.load_cycles()) == 90314
        traj = mc.load_trajectories()
        assert len(traj.cells) == 104
        assert list(mc.cv_splits("batch"))
        # read-only is enough: nothing was written
        assert sorted(p.name for p in directory.iterdir()) == sorted(C.REQUIRED_FILES)
    finally:
        directory.chmod(0o755)


def test_a_relative_path_and_a_tilde_are_accepted(good_copy, monkeypatch):
    monkeypatch.chdir(good_copy.parent)
    cells = mc.load_cells(data_dir=good_copy.name)
    assert len(cells) == 135
    assert cells.attrs["filters"]["data_dir"] == str(good_copy.resolve())
