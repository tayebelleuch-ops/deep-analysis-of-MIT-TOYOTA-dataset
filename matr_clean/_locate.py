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
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import tempfile
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
]


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
        path = directory / name
        actual = _sha256(path)
        expected = C.SHA256[name]
        if actual != expected:
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
                            C.SIZE_BYTES[name], path.stat().st_size
                            if path.exists() else 0
                        ),
                        "  The loader will not fall back to another source. Replace the"
                        " file with the one published at {0}".format(C.url_for(name)),
                        "  or point the loader elsewhere with set_data_dir() / {0}.".format(
                            C.DATA_DIR_ENV
                        ),
                    ]
                )
            )

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

def _download_one(name: str, target_dir: Path) -> Path:
    url = C.url_for(name)
    target = target_dir / name
    handle = tempfile.NamedTemporaryFile(
        dir=str(target_dir), prefix=".{0}.".format(name), suffix=".part", delete=False
    )
    tmp_path = Path(handle.name)
    try:
        with handle:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
                shutil.copyfileobj(response, handle)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    tmp_path.replace(target)
    return target


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
