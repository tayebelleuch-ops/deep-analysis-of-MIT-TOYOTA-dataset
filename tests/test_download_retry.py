"""The download retry: what is retried, what is not, and what is left on disk.

Nothing here touches the network. ``urlopen`` is replaced by a scripted stub whose
per-attempt behaviour is spelled out in each test: a read that stalls, a connection
the peer resets, a 503, or the real file. ``conftest`` stubs the backoff sleep, so the
retry path is exercised without waiting for it; the two tests that care about the
waits install their own recorder.
"""

from __future__ import annotations

import socket
import urllib.error
from pathlib import Path

import pytest

import matr_clean as mc
from matr_clean import _locate, constants as C


# ---------------------------------------------------------------------------
# a scripted urlopen
# ---------------------------------------------------------------------------

class _Response:
    """A readable response, optionally failing part-way through."""

    def __init__(self, path: Path, fail_after: int = -1, error: object = None):
        self._handle = open(str(path), "rb")
        self._fail_after = fail_after
        self._error = error
        self._served = 0

    def read(self, size: int = -1) -> bytes:
        if self._error is not None and self._served >= self._fail_after:
            raise self._error
        block = self._handle.read(size)
        self._served += len(block)
        return block

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._handle.close()
        return False


def _urlopen_script(source: Path, script):
    """Build a fake ``urlopen`` that follows *script* for each file it is asked for.

    *script* maps a filename to a list of per-attempt behaviours; a filename that is
    not in it is always served whole. Behaviours:

    ``"ok"``                serve the real file
    ``"stall"``             8 KB, then a read timeout (what a hung CDN looks like)
    ``"reset"``             8 KB, then ConnectionResetError
    ``("http", code)``      urlopen raises HTTPError with that status
    ``("truncate", n)``     serve only the first n bytes, cleanly
    """
    calls = []  # one entry per urlopen call: (filename, timeout)
    plans = {name: list(steps) for name, steps in script.items()}

    def fake_urlopen(url, timeout=None):
        name = url.rsplit("/", 1)[-1]
        calls.append((name, timeout))
        steps = plans.get(name)
        step = steps.pop(0) if steps else "ok"

        if step == "ok":
            return _Response(source / name)
        if step == "stall":
            return _Response(source / name, 8192, socket.timeout("timed out"))
        if step == "reset":
            return _Response(source / name, 8192, ConnectionResetError(104, "reset"))
        if isinstance(step, tuple) and step[0] == "http":
            raise urllib.error.HTTPError(url, step[1], "scripted", {}, None)
        if isinstance(step, tuple) and step[0] == "truncate":
            cut = (source / name).read_bytes()[: step[1]]
            partial = source.parent / ("partial_" + name)
            partial.write_bytes(cut)
            return _Response(partial)
        raise AssertionError("unknown step {0!r}".format(step))

    return fake_urlopen, calls


@pytest.fixture
def downloads(good_copy, monkeypatch):
    """Force step 5 (the cache) and return a scripted-urlopen installer."""
    monkeypatch.setattr(_locate, "_repo_exploration_dirs", lambda: [])

    def install(script):
        fake, calls = _urlopen_script(good_copy, script)
        monkeypatch.setattr(_locate.urllib.request, "urlopen", fake)
        return calls

    return install


def _attempts_for(calls, name):
    return [c for c in calls if c[0] == name]


def _leftovers(directory: Path):
    """Anything in the cache that is not one of the three finished files."""
    if not directory.exists():
        return []
    return sorted(
        p.name for p in directory.iterdir() if p.name not in C.REQUIRED_FILES
    )


# ---------------------------------------------------------------------------
# the four scenarios
# ---------------------------------------------------------------------------

def test_a_stalled_read_is_retried_and_then_succeeds(downloads):
    """A read that hangs past the timeout is the commonest transient failure."""
    calls = downloads({C.CYCLES_FILE: ["stall", "ok"]})

    cells = mc.load_cells()

    assert len(cells) == 135
    assert len(_attempts_for(calls, C.CYCLES_FILE)) == 2
    cache = C.cache_dir()
    assert sorted(p.name for p in cache.iterdir()) == sorted(C.REQUIRED_FILES)
    assert len(mc.load_cycles()) == 90314           # the retried file is complete


def test_a_connection_reset_is_retried(downloads):
    calls = downloads({C.CELLS_FILE: ["reset", "reset", "ok"]})

    assert len(mc.load_cells()) == 135
    assert len(_attempts_for(calls, C.CELLS_FILE)) == 3
    assert _leftovers(C.cache_dir()) == []


def test_a_503_is_retried_and_the_next_attempt_is_used(downloads):
    calls = downloads({C.INVENTORY_FILE: [("http", 503), "ok"]})

    assert len(mc.load_cells()) == 135
    assert len(_attempts_for(calls, C.INVENTORY_FILE)) == 2
    assert (C.cache_dir() / C.INVENTORY_FILE).is_file()


def test_a_persistent_failure_gives_up_after_max_attempts(downloads):
    """Four attempts, then the manual-download instructions -- not an infinite loop."""
    calls = downloads({C.CELLS_FILE: ["stall"] * 10})

    with pytest.raises(mc.DownloadError) as excinfo:
        mc.load_cells()

    assert len(_attempts_for(calls, C.CELLS_FILE)) == _locate.MAX_ATTEMPTS == 4
    # nothing was attempted for the later files: the first one never arrived
    assert _attempts_for(calls, C.CYCLES_FILE) == []

    message = str(excinfo.value)
    assert "{0} attempts failed".format(_locate.MAX_ATTEMPTS) in message
    # the wording the user is given has not changed
    for name in C.REQUIRED_FILES:
        assert C.url_for(name) in message
    assert "Download these three files by hand" in message
    assert C.DATA_DIR_ENV in message
    assert "set_data_dir" in message
    # and nothing is left on disk, not even a .part
    assert _leftovers(C.cache_dir()) == []
    assert not (C.cache_dir() / C.CELLS_FILE).exists()


# ---------------------------------------------------------------------------
# what must never be retried
# ---------------------------------------------------------------------------

def test_a_hash_mismatch_is_never_retried_and_the_file_is_deleted(downloads):
    """A truncated-but-clean download: the bytes are wrong, so a retry is pointless."""
    calls = downloads({C.CYCLES_FILE: [("truncate", 4096)] * 10})

    with pytest.raises(mc.IntegrityError) as excinfo:
        mc.load_cells()

    assert len(_attempts_for(calls, C.CYCLES_FILE)) == 1, "a wrong hash is final"
    message = str(excinfo.value)
    assert C.CYCLES_FILE in message
    assert C.SHA256[C.CYCLES_FILE] in message
    cache = C.cache_dir()
    assert not (cache / C.CYCLES_FILE).exists()      # the bad file is gone
    assert _leftovers(cache) == []
    assert not _attempts_for(calls, C.INVENTORY_FILE), "it stopped at the bad file"


@pytest.mark.parametrize("code", [403, 404, 410, 451])
def test_a_4xx_is_not_retried(downloads, code):
    calls = downloads({C.CELLS_FILE: [("http", code)] * 10})

    with pytest.raises(mc.DownloadError) as excinfo:
        mc.load_cells()

    assert len(_attempts_for(calls, C.CELLS_FILE)) == 1
    assert str(code) in str(excinfo.value)
    assert C.url_for(C.CELLS_FILE) in str(excinfo.value)


def test_an_unreachable_network_is_not_retried(downloads, monkeypatch):
    """Offline is not transient: the instructions should appear at once."""
    seen = []

    def offline(url, timeout=None):
        seen.append(url)
        raise urllib.error.URLError("Network is unreachable")

    downloads({})
    monkeypatch.setattr(_locate.urllib.request, "urlopen", offline)

    with pytest.raises(mc.DownloadError):
        mc.load_cells()
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# the policy itself
# ---------------------------------------------------------------------------

def test_the_per_attempt_timeout_is_longer_than_a_minute(downloads):
    calls = downloads({})
    mc.load_cells()
    assert calls, "nothing was downloaded"
    assert _locate.TIMEOUT_SECONDS > 60
    for name, timeout in calls:
        assert timeout == _locate.TIMEOUT_SECONDS


def test_the_backoff_grows_and_is_jittered():
    windows = [
        _locate.BACKOFF_BASE_SECONDS * 2 ** (n - 1)
        for n in range(1, _locate.MAX_ATTEMPTS)
    ]
    for n, window in enumerate(windows, start=1):
        draws = [_locate._retry_delay(n) for _ in range(200)]
        assert all(window / 2 <= d <= window for d in draws)   # within the window
        assert len(set(draws)) > 1                             # actually jittered
    # each window is twice the one before it, so the waits grow
    assert windows == sorted(windows) and windows[-1] > windows[0]
    # and the cap holds for an attempt far past MAX_ATTEMPTS
    assert _locate._retry_delay(50) <= _locate.BACKOFF_CAP_SECONDS


def test_the_waits_happen_between_attempts(downloads, monkeypatch):
    slept = []
    monkeypatch.setattr(_locate, "_sleep", lambda seconds: slept.append(seconds))
    calls = downloads({C.CELLS_FILE: ["stall", "reset", ("http", 500), "ok"]})

    assert len(mc.load_cells()) == 135
    assert len(_attempts_for(calls, C.CELLS_FILE)) == 4
    # three failures, three waits -- no wait after the attempt that succeeded
    assert len(slept) == 3
    assert all(s > 0 for s in slept)


def test_a_retry_leaves_no_part_file_behind_mid_flight(downloads):
    """Every failed attempt cleans up its own temporary file."""
    cache = C.cache_dir()
    seen_leftovers = []

    real_retry_delay = _locate._retry_delay

    def watch(attempt):
        seen_leftovers.append(_leftovers(cache))
        return real_retry_delay(attempt)

    _locate._retry_delay, saved = watch, _locate._retry_delay
    try:
        downloads({C.CYCLES_FILE: ["stall", "reset", "ok"]})
        assert len(mc.load_cells()) == 135
    finally:
        _locate._retry_delay = saved

    assert seen_leftovers == [[], []], "a .part file survived a failed attempt"
    assert _leftovers(cache) == []
