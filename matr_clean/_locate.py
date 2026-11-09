"""Find the three analysis-set CSVs, and prove they are the right ones.

Lookup order, first match wins:

1. an explicit ``data_dir=`` argument
2. a directory passed to :func:`set_data_dir` earlier in the session
3. the ``MATR_CLEAN_DATA_DIR`` environment variable
4. the repository's ``exploration/`` folder, when running from a clone
5. the download cache (``~/.cache/matr_clean``), fetching the files once from the
   raw-content URLs pinned to the ``v1.0`` tag

Every source is verified against :data:`matr_clean.constants.SHA256`, once per
process per directory. Nothing is ever written outside the cache: a directory the
user named (steps 1-3) and the repository's own ``exploration/`` folder are read-only
as far as this package is concerned.

A download is retried up to :data:`MAX_ATTEMPTS` times with exponential backoff and
jitter, but only for the reasons that a second attempt can actually fix -- a read or
connect timeout, a connection reset by the peer, an HTTP 5xx from the CDN. Nothing
else is retried: a 404, a redirect loop, an unreachable network and above all a
**hash mismatch** fail on the first attempt, because repeating them only wastes the
user's time. A file whose SHA-256 is wrong is deleted and the error raised. Downloads
land on a temporary ``.part`` file in the cache and are renamed into place only once
complete, so no attempt -- successful, failed or interrupted -- can leave a partial
file behind for a later run to mistake for the real thing.

The v1.1 within-cycle files (:func:`resolve_v11_dir`) use the same five steps, with
step 4 widened to the clone's ``exploration/extract_out/`` folder, which is where the
extraction writes them. They are resolved **independently** of the three v1.0 CSVs,
because the two sets normally sit in different directories, and they are hashed
against :data:`matr_clean.constants.V11_SHA256`.

Step 5 downloads them from the published Zenodo record, one file at a time and only
the files the caller actually asked for: a request for the two CSVs never fetches a
byte of the 2.20 GB of HDF5. Retry, backoff, the ``.part`` staging file and the
delete-on-mismatch rule are the same code as v1.0's, and the URL is always
``constants.v11_url_for``, which builds it from the record's own API listing.

Should the record constants ever be blanked, :func:`resolve_v11_dir` raises
:class:`DataDirError` naming the two routes that need no network -- ``data_dir=`` and
``$MATR_CLEAN_DATA_DIR`` -- before any socket call, rather than inventing a URL.
"""

from __future__ import annotations

import difflib
import hashlib
import http.client
import os
import random
import re
import socket
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import constants as C

__all__ = [
    "DataDirError",
    "IntegrityError",
    "DownloadError",
    "set_data_dir",
    "get_data_dir",
    "resolve_data_dir",
    "resolve_v11_dir",
]

#: Attempts per file, including the first. Four attempts span about 1 + 2 + 4
#: seconds of waiting at most, which rides out a CDN hiccup without making an
#: offline user wait.
MAX_ATTEMPTS = 4

#: Per-attempt socket timeout, in seconds. urllib applies it to the connect and to
#: every read, so this is the longest a single stalled read can hang. Deliberately
#: well above 60: the cycles file is 11 MB and a slow conference-wifi connection
#: should finish, not be abandoned.
TIMEOUT_SECONDS = 120.0

#: Backoff: attempt *n* waits between 50% and 100% of
#: ``BACKOFF_BASE_SECONDS * 2 ** (n - 1)``, capped at BACKOFF_CAP_SECONDS.
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0


class DataDirError(Exception):
    """A directory does not hold the three required analysis-set CSVs."""


class IntegrityError(Exception):
    """A file's SHA-256 does not match the value recorded for the ``v1.0`` tag."""


class DownloadError(Exception):
    """The files are not available locally and could not be downloaded."""


# Set by set_data_dir(); step 2 of the lookup order.
_SESSION_DIR = None  # type: Optional[Path]

# Directories whose three files have already been hashed in this process.
_VERIFIED = set()  # type: set

# Directories whose v1.1 files have already been hashed, as (directory, filename).
_V11_VERIFIED = set()  # type: set

# Indirection so a test can observe the waits without spending them.
_sleep = time.sleep


# ---------------------------------------------------------------------------
# hashing and verification
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise(name: str) -> str:
    """Strip the decorations a browser or file manager adds to a duplicate name."""
    stem = name.lower()
    stem = re.sub(r"\.csv$", "", stem)
    stem = re.sub(r"[\s_-]*\(?\d+\)?$", "", stem)
    stem = re.sub(r"[\s_-]*cop(y|ie)$", "", stem)
    return stem.strip()


def _similar_names(directory: Path, missing: List[str]) -> Dict[str, List[str]]:
    """Map each missing filename to names in *directory* that look like it.

    Catches the common cases: a second download saved as
    ``analysis_set_cycles (1).csv``, a rename to ``.CSV``, a stray copy suffix.
    """
    try:
        present = sorted(p.name for p in directory.iterdir() if p.is_file())
    except OSError:
        return {}

    hints = {}  # type: Dict[str, List[str]]
    for want in missing:
        want_key = _normalise(want)
        close = [p for p in present if _normalise(p) == want_key and p != want]
        if not close:
            close = difflib.get_close_matches(want, present, n=3, cutoff=0.6)
        if close:
            hints[want] = close
    return hints


def _missing_files(directory: Path) -> List[str]:
    return [name for name in C.REQUIRED_FILES if not (directory / name).is_file()]


def _describe_missing(directory: Path, missing: List[str], source: str) -> str:
    lines = [
        "{src} does not hold the analysis set.".format(src=source),
        "  directory: {0}".format(directory),
        "  missing:   {0}".format(", ".join(missing)),
    ]
    hints = _similar_names(directory, missing)
    if hints:
        lines.append(
            "  The directory does contain similarly named files. The loader needs the "
            "exact names; rename these:"
        )
        for want in sorted(hints):
            for found in hints[want]:
                lines.append("    {0!r}  ->  {1!r}".format(found, want))
    lines.append(
        "  Required, exactly: {0}".format(", ".join(C.REQUIRED_FILES))
    )
    return "\n".join(lines)


def _verify_one(path: Path, name: str, delete_on_mismatch: bool = False) -> None:
    """Hash one file and raise :class:`IntegrityError` if it is not the right one.

    A mismatch is never a transient failure, so a caller that is retrying must not
    retry this: the bytes at the pinned URL do not change, and a file that hashes
    wrong twice is wrong for a reason retrying cannot reach.
    """
    actual = _sha256(path)
    expected = C.SHA256[name]
    if actual == expected:
        return

    size = path.stat().st_size if path.exists() else 0
    if delete_on_mismatch:
        try:
            path.unlink()
        except OSError:
            pass
    raise IntegrityError(
        "\n".join(
            [
                "{name} does not match the file recorded for tag {tag}.".format(
                    name=name, tag=C.DATA_TAG
                ),
                "  path:     {0}".format(path),
                "  expected: {0}".format(expected),
                "  actual:   {0}".format(actual),
                "  Expected size: {0} bytes; this file: {1} bytes.".format(
                    C.SIZE_BYTES[name], size
                ),
                "  The loader will not fall back to another source. Replace the"
                " file with the one published at {0}".format(C.url_for(name)),
                "  or point the loader elsewhere with set_data_dir() / {0}.".format(
                    C.DATA_DIR_ENV
                ),
            ]
        )
    )


def _verify(directory: Path, source: str, delete_on_mismatch: bool = False) -> None:
    """Hash the three files in *directory* and compare against the constants.

    Skipped if *directory* has already been verified in this process.
    """
    key = str(directory)
    if key in _VERIFIED:
        return

    missing = _missing_files(directory)
    if missing:
        raise DataDirError(_describe_missing(directory, missing, source))

    for name in C.REQUIRED_FILES:
        _verify_one(directory / name, name, delete_on_mismatch=delete_on_mismatch)

    _VERIFIED.add(key)


# ---------------------------------------------------------------------------
# step 4: the repository's own exploration/ folder
# ---------------------------------------------------------------------------

def _repo_exploration_dirs() -> List[Path]:
    """Candidate ``exploration/`` folders, when this is running inside a clone.

    Two starting points are walked upwards: the installed package itself (which is
    inside the clone after ``pip install -e .``) and the current working directory
    (which covers a non-editable install used from inside a clone).
    """
    candidates = []  # type: List[Path]
    starts = [Path(__file__).resolve().parent]
    try:
        starts.append(Path.cwd().resolve())
    except OSError:
        pass

    for start in starts:
        for parent in [start] + list(start.parents):
            exploration = parent / "exploration"
            if (exploration / C.CELLS_FILE).is_file() and (
                exploration / "REPORT.md"
            ).is_file():
                if exploration not in candidates:
                    candidates.append(exploration)
    return candidates


# ---------------------------------------------------------------------------
# step 5: the download cache
# ---------------------------------------------------------------------------

def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


#: Reasons worth another attempt, when the exception carries a string rather than a
#: nested exception (some proxies and older urllib paths report it that way).
_RETRYABLE_TEXT = re.compile(
    r"timed out|timeout|connection reset|reset by peer|connection aborted"
    r"|broken pipe|temporarily unavailable|incomplete read",
    re.IGNORECASE,
)


def _retryable_reason(exc: BaseException, _depth: int = 0) -> Optional[str]:
    """Return a short label if *exc* is worth retrying, else ``None``.

    Only three things are: a timeout, a connection the peer dropped, and an HTTP 5xx.
    Everything else -- 404, 403, a redirect loop, an unreachable network, a full disk
    -- would fail the same way on the next attempt, and an offline user should see the
    manual-download instructions at once rather than after four waits.
    """
    if isinstance(exc, urllib.error.HTTPError):
        try:
            code = int(exc.code)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
        return "HTTP {0}".format(code) if 500 <= code <= 599 else None

    # socket.timeout is TimeoutError from 3.10 on, a bare OSError before it.
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, ConnectionResetError):
        return "connection reset"
    if isinstance(exc, ConnectionAbortedError):
        return "connection aborted"
    if isinstance(exc, (http.client.IncompleteRead, http.client.BadStatusLine)):
        return "truncated response"

    if isinstance(exc, urllib.error.URLError) and _depth < 3:
        reason = exc.reason
        if isinstance(reason, BaseException):
            return _retryable_reason(reason, _depth + 1)
        if isinstance(reason, str) and _RETRYABLE_TEXT.search(reason):
            return reason.strip()
        return None

    if _depth < 3 and isinstance(exc.__cause__, BaseException):
        return _retryable_reason(exc.__cause__, _depth + 1)
    return None


def _retry_delay(attempt: int) -> float:
    """Seconds to wait after a failed *attempt* (1-based).

    Exponential with equal jitter: half the window is fixed so the waits still grow,
    half is random so a roomful of clones that failed together do not come back in
    step. Capped, so a long MAX_ATTEMPTS could never wait minutes.
    """
    window = min(
        BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_CAP_SECONDS
    )
    return window * (0.5 + 0.5 * random.random())


#: Read size for a download body. One MiB, as for hashing.
COPY_BLOCK_BYTES = 1024 * 1024


def _declared_length(response) -> Optional[int]:
    """The response's ``Content-Length``, if it gave a usable one."""
    headers = getattr(response, "headers", None)
    raw = headers.get("Content-Length") if headers is not None else None
    try:
        length = int(raw)
    except (TypeError, ValueError):
        return None
    return length if length >= 0 else None


def _fetch_once(url: str, target: Path, expected_bytes: Optional[int] = None) -> None:
    """One attempt: download *url* to *target*, atomically or not at all.

    The bytes go to a ``.part`` temporary file in the same directory and are renamed
    over *target* only after the response is fully read, so a failed or interrupted
    attempt leaves nothing behind that looks like a finished file.

    **A short body is caught here, not left to the hash check.**
    ``http.client.HTTPResponse.read(amt)`` returns ``b""`` instead of raising when the
    connection drops mid-body -- CPython says so in a comment: raising
    ``IncompleteRead`` there "might break compatibility". So a transfer cut at 97% of
    a 72.8 MB file looks, to any plain copy loop, exactly like a file that ended.
    Left alone, that surfaces as an :class:`IntegrityError`, which tells the user
    their data is corrupt -- final, not retried -- when what actually happened is the
    one thing a retry does fix. Counting the bytes and comparing them against
    ``Content-Length`` (or, if the server gave none, the size recorded in the
    manifest) turns it back into the transient failure it is.
    """
    handle = tempfile.NamedTemporaryFile(
        dir=str(target.parent),
        prefix=".{0}.".format(target.name),
        suffix=".part",
        delete=False,
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                declared = _declared_length(response)
                written = 0
                while True:
                    block = response.read(COPY_BLOCK_BYTES)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)

        wanted = declared if declared is not None else expected_bytes
        if wanted is not None and written < wanted:
            raise http.client.IncompleteRead(b"", wanted - written)

        tmp_path.replace(target)
    except BaseException:
        _unlink_quietly(tmp_path)
        raise


def _download_one(name: str, target_dir: Path) -> Path:
    """Download one required file into *target_dir* and verify it.

    Retries what a second attempt can fix, up to :data:`MAX_ATTEMPTS` times. The
    downloaded file is hashed immediately: a mismatch deletes it and raises
    :class:`IntegrityError` without a retry, and without downloading the rest.
    """
    url = C.url_for(name)
    target = target_dir / name

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _fetch_once(url, target, C.SIZE_BYTES.get(name))
        except Exception as exc:  # classified, then re-raised or retried
            label = _retryable_reason(exc)
            if label is None:
                raise DownloadError(_offline_message("{0}: {1}".format(name, exc)))
            if attempt == MAX_ATTEMPTS:
                raise DownloadError(
                    _offline_message(
                        "{0}: {1} attempts failed, last {2} ({3})".format(
                            name, MAX_ATTEMPTS, label, exc
                        )
                    )
                )
            _sleep(_retry_delay(attempt))
            continue
        # Downloaded cleanly. A wrong hash is final, so this sits outside the retry.
        _verify_one(target, name, delete_on_mismatch=True)
        return target

    raise AssertionError("unreachable")  # pragma: no cover


def _offline_message(reason: str) -> str:
    lines = [
        "The analysis set is not available locally and could not be downloaded.",
        "  reason: {0}".format(reason),
        "",
        "Download these three files by hand (they total about 11 MB):",
    ]
    for name in C.REQUIRED_FILES:
        lines.append("  {0}".format(C.url_for(name)))
    lines += [
        "",
        "Put all three in one directory, keeping these exact names:",
        "  {0}".format(", ".join(C.REQUIRED_FILES)),
        "",
        "Then point the loader at it, either",
        "  export {0}=/path/to/that/directory".format(C.DATA_DIR_ENV),
        "or, in Python,",
        "  import matr_clean; matr_clean.set_data_dir('/path/to/that/directory')",
    ]
    return "\n".join(lines)


def _populate_cache() -> Path:
    cache = C.cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(_offline_message("cannot create {0}: {1}".format(cache, exc)))

    if not _missing_files(cache):
        _verify(cache, "the download cache", delete_on_mismatch=True)
        return cache

    for name in C.REQUIRED_FILES:
        if (cache / name).is_file():
            continue
        try:
            _download_one(name, cache)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # _download_one raises DownloadError itself for anything it saw; this
            # catches what it could not, e.g. a full disk during the rename.
            raise DownloadError(
                _offline_message("{0}: {1}".format(name, exc))
            )

    _verify(cache, "the download cache", delete_on_mismatch=True)
    return cache


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def set_data_dir(path) -> Path:
    """Use *path* as the analysis-set directory for the rest of this session.

    The three CSVs are checked and hashed immediately, so a wrong path fails here
    rather than at the first load. The directory is only ever read from.

    Returns the resolved path.
    """
    directory = Path(path).expanduser().resolve()
    _verify(directory, "The directory passed to set_data_dir()")
    global _SESSION_DIR
    _SESSION_DIR = directory
    return directory


def get_data_dir() -> Optional[Path]:
    """Return the directory set by :func:`set_data_dir`, or ``None``."""
    return _SESSION_DIR


def resolve_data_dir(data_dir=None, _allow_download: bool = True) -> Tuple[Path, str]:
    """Return ``(directory, source_label)`` for a verified analysis-set directory.

    Raises rather than falling back whenever the user named a directory explicitly
    (steps 1-3): a wrong path is a mistake worth seeing, not a reason to silently
    read different data.
    """
    if data_dir is not None:
        directory = Path(data_dir).expanduser().resolve()
        _verify(directory, "The directory passed as data_dir=")
        return directory, "data_dir= argument"

    if _SESSION_DIR is not None:
        _verify(_SESSION_DIR, "The directory passed to set_data_dir()")
        return _SESSION_DIR, "set_data_dir()"

    from_env = os.environ.get(C.DATA_DIR_ENV)
    if from_env:
        directory = Path(from_env).expanduser().resolve()
        _verify(
            directory,
            "The directory named by {0}".format(C.DATA_DIR_ENV),
        )
        return directory, "${0}".format(C.DATA_DIR_ENV)

    for exploration in _repo_exploration_dirs():
        _verify(exploration, "The repository's exploration/ folder")
        return exploration, "the repository's exploration/ folder"

    cache = C.cache_dir()
    if not _missing_files(cache):
        _verify(cache, "the download cache", delete_on_mismatch=True)
        return cache, "the download cache ({0})".format(cache)

    if not _allow_download:
        raise DownloadError(_offline_message("downloads are disabled"))

    return _populate_cache(), "the download cache ({0}, just downloaded)".format(cache)


# ===========================================================================
# v1.1: the within-cycle files
# ===========================================================================
# Resolved separately from the three v1.0 CSVs. In a clone the two sets live in
# different folders -- exploration/ and exploration/extract_out/ -- and a user who
# points data_dir= at one of them should not be told the other is missing.


def _missing_v11_files(directory: Path, names) -> List[str]:
    return [name for name in names if not (directory / name).is_file()]


def _verify_v11_one(path: Path, name: str, delete_on_mismatch: bool = False) -> None:
    """Hash one v1.1 file against :data:`constants.V11_SHA256`.

    As for v1.0, a mismatch is never transient and is never retried.
    """
    key = (str(path.parent), name)
    if key in _V11_VERIFIED:
        return

    actual = _sha256(path)
    expected = C.V11_SHA256[name]
    if actual == expected:
        _V11_VERIFIED.add(key)
        return

    size = path.stat().st_size if path.exists() else 0
    if delete_on_mismatch:
        _unlink_quietly(path)
    raise IntegrityError(
        "\n".join(
            [
                "{name} does not match the file recorded in "
                "exploration/MANIFEST_v1.1.md.".format(name=name),
                "  path:     {0}".format(path),
                "  expected: {0}".format(expected),
                "  actual:   {0}".format(actual),
                "  Expected size: {0} bytes; this file: {1} bytes.".format(
                    C.V11_SIZE_BYTES[name], size
                ),
                "  The extraction is byte-reproducible, so a correctly regenerated"
                " file hashes to the expected value.",
                "  The loader will not fall back to another source.",
            ]
        )
    )


def _verify_v11(
    directory: Path, source: str, names, delete_on_mismatch: bool = False
) -> None:
    missing = _missing_v11_files(directory, names)
    if missing:
        lines = [
            "{src} does not hold the v1.1 within-cycle files.".format(src=source),
            "  directory: {0}".format(directory),
            "  missing:   {0}".format(", ".join(missing)),
        ]
        hints = _similar_names(directory, missing)
        if hints:
            lines.append(
                "  The directory does contain similarly named files. The loader needs"
                " the exact names; rename these:"
            )
            for want in sorted(hints):
                for found in hints[want]:
                    lines.append("    {0!r}  ->  {1!r}".format(found, want))
        lines.append("  Required, exactly: {0}".format(", ".join(names)))
        lines.append(
            "  In a clone these are written to exploration/extract_out/ by"
            " exploration/extract_within_cycle.py."
        )
        raise DataDirError("\n".join(lines))

    for name in names:
        _verify_v11_one(
            directory / name, name, delete_on_mismatch=delete_on_mismatch
        )


def _repo_v11_dirs(names) -> List[Path]:
    """Candidate v1.1 folders inside a clone.

    ``exploration/extract_out/`` first, because that is where the extraction writes;
    then ``exploration/`` itself, for someone who moved the files up a level.
    """
    candidates = []  # type: List[Path]
    starts = [Path(__file__).resolve().parent]
    try:
        starts.append(Path.cwd().resolve())
    except OSError:
        pass

    for start in starts:
        for parent in [start] + list(start.parents):
            exploration = parent / "exploration"
            if not (exploration / "REPORT.md").is_file():
                continue
            for folder in (exploration / "extract_out", exploration):
                if not _missing_v11_files(folder, names) and folder not in candidates:
                    candidates.append(folder)
    return candidates


def _v11_unpublished_message() -> str:
    """The message raised when there is no record to download from.

    The published record makes this unreachable in a normal install. It is kept,
    and kept tested, because it is the behaviour the package falls back to if
    ``constants.V11_ZENODO_*`` is ever blanked -- a fork pointing at a record of
    its own, or a future revision caught mid-edit. The rule it encodes is the point:
    never invent a URL, and say which routes work without one.
    """
    return "\n".join(
        [
            "v1.1 data not yet published; use data_dir= or {env}.".format(
                env=C.DATA_DIR_ENV
            ),
            "",
            "This build of matr_clean carries no Zenodo record for the within-cycle"
            " extraction, so it has no file URLs and cannot download it.",
            "Everything local works. Point the loader at a directory holding"
            " {0}:".format(" and ".join(C.V11_REQUIRED_FILES)),
            "  export {0}=/path/to/that/directory".format(C.DATA_DIR_ENV),
            "or, in Python,",
            "  import matr_clean; matr_clean.load_cycle_features(data_dir='/path/...')",
            "",
            "In a clone of the repository the files are found automatically at"
            " exploration/extract_out/, with no configuration at all.",
        ]
    )


def _human_bytes(count: int) -> str:
    """``797659714`` -> ``'797.7 MB'``. Error messages only.

    Decimal MB and GB, because that is what MANIFEST_v1.1.md, EXTRACTION.md and
    USAGE.md quote ("72.8 MB", "2.20 GB"); printing MiB here would make the loader
    disagree with every document describing the same files.
    """
    if count >= 10 ** 9:
        return "{0:.2f} GB".format(count / 1e9)
    if count >= 10 ** 6:
        return "{0:.1f} MB".format(count / 1e6)
    return "{0:.1f} kB".format(count / 1e3)


def _v11_offline_message(reason: str) -> str:
    """What to say when a v1.1 file could not be fetched from the record.

    Deliberately not :func:`_offline_message`: that one names the three v1.0 CSVs
    and their raw-content URLs, which is the wrong instruction for someone whose
    index download just failed.
    """
    lines = [
        "The v1.1 within-cycle data is not available locally and could not be"
        " downloaded.",
        "  reason: {0}".format(reason),
        "",
        "It is published, with a DOI, at",
        "  {0}".format(C.V11_ZENODO_RECORD_URL),
        "  DOI {0}  (version {1})".format(C.V11_ZENODO_DOI,
                                          C.V11_ZENODO_VERSION_LABEL),
        "",
        "Download by hand what you need -- the two CSVs are enough for the"
        " DataFrame loaders:",
    ]
    for name in C.V11_ALL_DATA_FILES:
        lines.append(
            "  {0:>9}  {1}".format(
                _human_bytes(C.V11_SIZE_BYTES[name]), C.v11_url_for(name)
            )
        )
    lines += [
        "",
        "The three .h5 files total {0} and are fetched only when something asks"
        " for them.".format(_human_bytes(C.V11_H5_TOTAL_BYTES)),
        "",
        "Put the files in one directory, keeping these exact names, then point the"
        " loader at it, either",
        "  export {0}=/path/to/that/directory".format(C.DATA_DIR_ENV),
        "or, in Python,",
        "  import matr_clean"
        "; matr_clean.load_cycle_features(v11_dir='/path/to/that/directory')",
    ]
    return "\n".join(lines)


def _download_v11_one(name: str, target_dir: Path) -> Path:
    """Download one v1.1 file into *target_dir* and verify it.

    The v1.0 rules, unchanged: retry only what a second attempt can fix, hash the
    result immediately, and treat a wrong hash as final -- delete it, raise, and do
    not fetch the rest.
    """
    url = C.v11_url_for(name)
    target = target_dir / name

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _fetch_once(url, target, C.V11_SIZE_BYTES.get(name))
        except Exception as exc:  # classified, then re-raised or retried
            label = _retryable_reason(exc)
            if label is None:
                raise DownloadError(
                    _v11_offline_message("{0}: {1}".format(name, exc))
                )
            if attempt == MAX_ATTEMPTS:
                raise DownloadError(
                    _v11_offline_message(
                        "{0}: {1} attempts failed, last {2} ({3})".format(
                            name, MAX_ATTEMPTS, label, exc
                        )
                    )
                )
            _sleep(_retry_delay(attempt))
            continue
        # Downloaded cleanly. A wrong hash is final, so this sits outside the retry.
        _verify_v11_one(target, name, delete_on_mismatch=True)
        return target

    raise AssertionError("unreachable")  # pragma: no cover


def _populate_v11_cache(names) -> Path:
    """Fetch the missing files of *names* into the cache and verify all of them.

    Only *names* is fetched. ``resolve_v11_dir`` is called with the filenames one
    caller needs -- the two CSVs, or a single batch's ``.h5`` -- so nothing ever
    downloads 2.20 GB to answer a question about one batch.
    """
    cache = C.cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(
            _v11_offline_message("cannot create {0}: {1}".format(cache, exc))
        )

    for name in names:
        if (cache / name).is_file():
            continue
        try:
            _download_v11_one(name, cache)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # _download_v11_one raises DownloadError itself for anything it saw;
            # this catches what it could not, e.g. a full disk during the rename.
            raise DownloadError(
                _v11_offline_message("{0}: {1}".format(name, exc))
            )

    _verify_v11(cache, "the download cache", names, delete_on_mismatch=True)
    return cache


def resolve_v11_dir(data_dir=None, names=None) -> Tuple[Path, str]:
    """Return ``(directory, source_label)`` for a verified v1.1 data directory.

    The lookup order is v0.1.1's, with step 4 widened to the clone's
    ``exploration/extract_out/``. As for v1.0, a directory the user named explicitly
    raises rather than falling back: a wrong path is a mistake worth seeing. Step 5
    downloads the missing files of *names* from the published Zenodo record into the
    cache, and nothing else -- a clone or a named folder is never written to.

    *names* defaults to :data:`constants.V11_REQUIRED_FILES`, the two CSVs v0.2.0
    reads. :func:`matr_clean.load_series` passes the HDF5 filenames it needs instead,
    one or two batches at a time, so a user with only one batch on disk is not told
    the other two are missing and never fetches 2.20 GB to answer a question about
    0.58 GB.
    """
    if names is None:
        names = C.V11_REQUIRED_FILES
    names = tuple(names)

    if data_dir is not None:
        directory = Path(data_dir).expanduser().resolve()
        _verify_v11(directory, "The directory passed as data_dir=", names)
        return directory, "data_dir= argument"

    if _SESSION_DIR is not None:
        _verify_v11(_SESSION_DIR, "The directory passed to set_data_dir()", names)
        return _SESSION_DIR, "set_data_dir()"

    from_env = os.environ.get(C.DATA_DIR_ENV)
    if from_env:
        directory = Path(from_env).expanduser().resolve()
        _verify_v11(
            directory, "The directory named by {0}".format(C.DATA_DIR_ENV), names
        )
        return directory, "${0}".format(C.DATA_DIR_ENV)

    for folder in _repo_v11_dirs(names):
        _verify_v11(folder, "The repository's {0} folder".format(folder.name), names)
        return folder, "the repository's {0}/ folder".format(folder.name)

    cache = C.cache_dir()
    if not _missing_v11_files(cache, names):
        _verify_v11(cache, "the download cache", names, delete_on_mismatch=True)
        return cache, "the download cache ({0})".format(cache)

    # Step 5 proper: fetch the missing files from the published record.
    if not C.v11_is_published():
        raise DataDirError(_v11_unpublished_message())

    _populate_v11_cache(names)
    return cache, "the download cache ({0}, just downloaded)".format(cache)
