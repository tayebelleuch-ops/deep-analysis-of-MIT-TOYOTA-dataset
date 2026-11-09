"""Step 5 for the v1.1 files: the Zenodo download route.

Nothing here reaches the network. ``urlopen`` is replaced by a stub that serves the
committed fixture bytes, and the fixture's own hashes are patched into
``constants.V11_SHA256`` by the ``v11_fixture_hashes`` fixture, so the whole
fetch-stage-rename-hash path runs for real against bytes small enough to commit.

Two tests do use the network, and both are opt-in behind
``MATR_CLEAN_TEST_NETWORK=1``: one fetches ``within_cycle_cells.csv`` (14.4 kB)
through the ordinary route and checks it hashes to the manifest value, the other
re-reads the record's files listing and asserts the URL, size and MD5 of all five
loadable files are still the ones ``constants.py`` carries. Both are skipped by
default, so the suite stays offline and deterministic.
"""

from __future__ import annotations

import io
import os
import shutil
import urllib.error
from pathlib import Path

import pytest

import matr_clean as mc
from matr_clean import _locate
from matr_clean import constants as C


FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# a urlopen that serves the fixtures, and records the URLs it was given
# ---------------------------------------------------------------------------

class _Served(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _v11_serve(script=None, source=FIXTURES):
    """Fake ``urlopen`` for v1.1 URLs. *script* maps a filename to behaviours.

    Behaviours, consumed one per attempt: ``"ok"`` serves the fixture bytes,
    ``"corrupt"`` serves them with one byte changed, ``("http", code)`` raises that
    status, and an exception instance is raised as given.
    """
    script = {name: list(steps) for name, steps in (script or {}).items()}
    urls = []

    def fake_urlopen(url, timeout=None):
        urls.append(url)
        # .../files/<name>/content -- the name is the penultimate segment
        name = url.rstrip("/").rsplit("/", 2)[-2]
        steps = script.get(name)
        step = steps.pop(0) if steps else "ok"

        if step == "ok":
            return _Served((source / name).read_bytes())
        if step == "corrupt":
            data = bytearray((source / name).read_bytes())
            data[0] = (data[0] + 1) % 256
            return _Served(bytes(data))
        if isinstance(step, tuple) and step[0] == "http":
            raise urllib.error.HTTPError(url, step[1], "scripted", {}, None)
        if isinstance(step, BaseException):
            raise step
        raise AssertionError("unknown step {0!r}".format(step))

    return fake_urlopen, urls


@pytest.fixture
def v11_fixture_hashes(monkeypatch):
    """Point V11_SHA256/V11_SIZE_BYTES at the committed fixture's own values.

    The same trick the ``v11_dir`` fixture uses: the verification path stays under
    test rather than bypassed, which is what makes the corruption tests meaningful.
    """
    for name in C.V11_REQUIRED_FILES:
        path = FIXTURES / name
        monkeypatch.setitem(C.V11_SHA256, name, _locate._sha256(path))
        monkeypatch.setitem(C.V11_SIZE_BYTES, name, path.stat().st_size)


@pytest.fixture
def downloads_v11(monkeypatch, no_local_v11, v11_fixture_hashes):
    """Force step 5 for the v1.1 files and return a scripted-urlopen installer."""
    def install(script=None):
        fake, urls = _v11_serve(script)
        monkeypatch.setattr(_locate.urllib.request, "urlopen", fake)
        return urls

    return install


def _cache_contents():
    cache = C.cache_dir()
    if not cache.exists():
        return []
    return sorted(p.name for p in cache.iterdir())


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------

def test_the_two_csvs_are_downloaded_verified_and_cached(downloads_v11):
    urls = downloads_v11()
    directory, source = _locate.resolve_v11_dir(None)

    assert directory == C.cache_dir()
    assert "just downloaded" in source
    assert sorted(_cache_contents()) == sorted(C.V11_REQUIRED_FILES)
    # the URLs came from constants, not from anything assembled here
    assert urls == [C.v11_url_for(name) for name in C.V11_REQUIRED_FILES]
    for url in urls:
        assert url.startswith(C.V11_ZENODO_BASE + "/")
        assert url.endswith("/content")


def test_only_the_requested_names_are_fetched(downloads_v11):
    """A caller asking for one file must not pull 2.20 GB of HDF5 with it."""
    urls = downloads_v11()
    _locate.resolve_v11_dir(None, names=(C.V11_CELLS_FILE,))
    assert urls == [C.v11_url_for(C.V11_CELLS_FILE)]
    assert _cache_contents() == [C.V11_CELLS_FILE]
    for name in C.V11_H5_FILES.values():
        assert name not in " ".join(urls)


def test_a_second_call_reuses_the_cache_without_downloading(downloads_v11):
    urls = downloads_v11()
    _locate.resolve_v11_dir(None)
    first = len(urls)
    assert first == len(C.V11_REQUIRED_FILES)

    _locate._V11_VERIFIED.clear()
    directory, source = _locate.resolve_v11_dir(None)
    assert len(urls) == first, "the second call went back to the network"
    assert directory == C.cache_dir()
    assert "just downloaded" not in source


def test_the_downloaded_file_is_the_published_one(downloads_v11):
    downloads_v11()
    directory, _ = _locate.resolve_v11_dir(None)
    for name in C.V11_REQUIRED_FILES:
        assert _locate._sha256(directory / name) == C.V11_SHA256[name]
    # and it is usable, not merely present
    frame = mc.load_cycle_features(v11_dir=directory,
                                   data_dir=_repo_exploration())
    assert len(frame) > 0


def _repo_exploration():
    for parent in Path(__file__).resolve().parents:
        if (parent / "exploration" / "REPORT.md").is_file():
            return parent / "exploration"
    raise RuntimeError("not in a clone")


# ---------------------------------------------------------------------------
# the error paths
# ---------------------------------------------------------------------------

def test_a_blocked_network_fails_once_and_says_where_the_files_are(downloads_v11):
    """What an offline or firewalled user sees. No retry: four waits would not
    turn a refused connection into a download."""
    refused = urllib.error.URLError(ConnectionRefusedError(111, "refused"))
    urls = downloads_v11({C.V11_INDEX_FILE: [refused, refused, refused, refused],
                          C.V11_CELLS_FILE: [refused, refused, refused, refused]})

    with pytest.raises(mc.DownloadError) as excinfo:
        _locate.resolve_v11_dir(None)

    assert len(urls) == 1, "a refused connection was retried"
    message = str(excinfo.value)
    assert "could not be downloaded" in message
    assert C.V11_ZENODO_RECORD_URL in message
    assert C.V11_ZENODO_DOI in message
    assert C.DATA_DIR_ENV in message
    assert "v11_dir=" in message
    for name in C.V11_ALL_DATA_FILES:
        assert C.v11_url_for(name) in message
    assert "2.20 GB" in message          # the .h5 total, decimal as everywhere else
    assert _cache_contents() == [], "a failed download left something behind"


def test_a_5xx_is_retried_and_then_succeeds(downloads_v11):
    urls = downloads_v11({C.V11_INDEX_FILE: [("http", 503), ("http", 502), "ok"]})
    directory, _ = _locate.resolve_v11_dir(None)
    index_urls = [u for u in urls if C.V11_INDEX_FILE in u]
    assert len(index_urls) == 3
    assert _locate._sha256(directory / C.V11_INDEX_FILE) == C.V11_SHA256[
        C.V11_INDEX_FILE
    ]


def test_a_wrong_hash_is_not_retried_and_leaves_nothing(downloads_v11):
    urls = downloads_v11({C.V11_CELLS_FILE: ["corrupt", "ok"]})
    with pytest.raises(mc.IntegrityError) as excinfo:
        _locate.resolve_v11_dir(None, names=(C.V11_CELLS_FILE,))

    assert len([u for u in urls if C.V11_CELLS_FILE in u]) == 1
    message = str(excinfo.value)
    assert "MANIFEST_v1.1.md" in message
    assert "byte-reproducible" in message
    assert _cache_contents() == [], "the corrupt download was kept"


def test_a_corrupted_cache_is_rejected_and_discarded(downloads_v11,
                                                     v11_fixture_hashes):
    """The cache is the one directory the loader may delete from: a file that no
    longer hashes to the manifest value is removed, so the next run refetches it
    instead of reading it forever."""
    cache = C.cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    for name in C.V11_REQUIRED_FILES:
        shutil.copy2(FIXTURES / name, cache / name)
    good = (cache / C.V11_CELLS_FILE).read_bytes()
    (cache / C.V11_CELLS_FILE).write_bytes(good[:-1])

    urls = downloads_v11()
    with pytest.raises(mc.IntegrityError) as excinfo:
        _locate.resolve_v11_dir(None)
    assert "expected:" in str(excinfo.value)
    assert urls == [], "the loader downloaded before checking what it had"
    assert not (cache / C.V11_CELLS_FILE).exists(), "the bad file was kept"
    assert (cache / C.V11_INDEX_FILE).exists(), "a good cached file was discarded"

    # and the next call repairs it
    _locate._V11_VERIFIED.clear()
    directory, source = _locate.resolve_v11_dir(None)
    assert urls == [C.v11_url_for(C.V11_CELLS_FILE)]
    assert directory == cache
    assert _locate._sha256(cache / C.V11_CELLS_FILE) == C.V11_SHA256[
        C.V11_CELLS_FILE
    ]


def test_a_user_folder_is_never_repaired_only_the_cache(tmp_path, v11_dir):
    """delete_on_mismatch is the cache's rule alone. A directory the user named
    keeps its files, corrupt or not."""
    target = tmp_path / "mine"
    target.mkdir()
    for name in C.V11_REQUIRED_FILES:
        shutil.copy2(v11_dir / name, target / name)
    victim = target / C.V11_CELLS_FILE
    victim.write_bytes(victim.read_bytes()[:-1])

    with pytest.raises(mc.IntegrityError):
        _locate.resolve_v11_dir(target)
    assert victim.exists(), "the loader deleted from a folder the user named"


# ---------------------------------------------------------------------------
# opt-in: the real record
# ---------------------------------------------------------------------------

NETWORK_ENV = "MATR_CLEAN_TEST_NETWORK"


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get(NETWORK_ENV) != "1",
    reason="set {0}=1 to fetch 14.4 kB from the published Zenodo record".format(
        NETWORK_ENV
    ),
)
def test_the_published_record_serves_the_file_it_says_it_does(no_local_v11):
    """The only test that touches the network, and the only one that proves the
    URL in constants.py is the one Zenodo actually serves bytes from.

    Fetches the smallest file in the record (14.4 kB) through the ordinary route,
    so a URL shape that 404s, or a record that was superseded, fails here.
    """
    directory, source = _locate.resolve_v11_dir(None, names=(C.V11_CELLS_FILE,))
    assert directory == C.cache_dir()
    assert "just downloaded" in source
    assert _locate._sha256(directory / C.V11_CELLS_FILE) == C.V11_SHA256[
        C.V11_CELLS_FILE
    ]
    assert (directory / C.V11_CELLS_FILE).stat().st_size == C.V11_SIZE_BYTES[
        C.V11_CELLS_FILE
    ]


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get(NETWORK_ENV) != "1",
    reason="set {0}=1 to read the record's files listing (a few kB of JSON)".format(
        NETWORK_ENV
    ),
)
def test_the_constants_still_match_the_records_own_file_listing():
    """Where every value in the Zenodo block came from, re-read.

    ``constants.py`` was filled from ``GET /api/records/23984188/files`` rather than
    from a URL pattern, and this is the test that says so in executable form: the
    download URL must be the listing's own ``links.content``, and the size and MD5
    of all five loadable files must be the listing's. A superseded record, a
    renamed file or a re-upload fails here.
    """
    import json
    import urllib.request

    url = C.V11_ZENODO_BASE
    with urllib.request.urlopen(url, timeout=60) as response:
        listing = json.load(response)

    entries = {entry["key"]: entry for entry in listing["entries"]}
    for name in sorted(C.V11_SHA256):
        assert name in entries, "{0} is no longer in the record".format(name)
        entry = entries[name]
        assert entry["links"]["content"] == C.v11_url_for(name), name
        assert entry["size"] == C.V11_SIZE_BYTES[name], name
        assert entry["checksum"] == "md5:" + C.V11_ZENODO_MD5[name], name
        assert entry["status"] == "completed", name

    # the three the loader never reads are still there, and still not claimed
    for name in ("SHA256SUMS.txt", "EXTRACTION.md", "LICENSE.txt"):
        assert name in entries
        assert name not in C.V11_SHA256
    assert len(entries) == 8
