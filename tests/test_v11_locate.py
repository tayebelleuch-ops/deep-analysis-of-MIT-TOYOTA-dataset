"""Finding the v1.1 files, and the one error raised while Zenodo is a draft."""

from __future__ import annotations

import shutil

import pytest

import matr_clean as mc
from matr_clean import _locate
from matr_clean import constants as C


# ---------------------------------------------------------------------------
# the Zenodo placeholders
# ---------------------------------------------------------------------------

def test_the_record_is_not_published():
    """Guards against someone filling one placeholder and forgetting the rest."""
    assert C.V11_ZENODO_DOI is None
    assert C.V11_ZENODO_RECORD_ID is None
    assert C.V11_ZENODO_BASE is None
    assert C.V11_DATA_TAG is None
    assert C.v11_is_published() is False


def test_unpublished_names_both_routes_that_work(no_local_v11):
    with pytest.raises(mc.DataDirError) as excinfo:
        _locate.resolve_v11_dir(None)
    message = str(excinfo.value)
    assert message.splitlines()[0] == (
        "v1.1 data not yet published; use data_dir= or MATR_CLEAN_DATA_DIR."
    )
    assert "data_dir=" in message
    assert C.DATA_DIR_ENV in message
    assert "exploration/extract_out/" in message


def test_a_named_directory_reports_what_is_missing_there(tmp_path):
    """A directory the user named explicitly gets a specific error, not the
    generic unpublished one: a wrong path is a mistake worth seeing."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(mc.DataDirError) as excinfo:
        mc.load_cycle_features(v11_dir=empty)
    message = str(excinfo.value)
    assert "does not hold the v1.1 within-cycle files" in message
    assert C.V11_INDEX_FILE in message
    assert "exploration/extract_within_cycle.py" in message


def test_local_data_in_the_clone_is_found_and_beats_the_unpublished_error(
    exploration_dir, v11_dir, monkeypatch
):
    """The other half of the same behaviour, which no test covered before.

    With v1.1 files reachable through step 4 of the lookup order, resolution must
    succeed rather than raise "not yet published" -- the record being a draft says
    nothing about what is on disk. This is what fails if ``_repo_v11_dirs`` is ever
    narrowed, and it is why the two tests above have to opt out of the clone lookup
    explicitly instead of assuming an empty checkout.
    """
    monkeypatch.setattr(
        _locate, "_repo_v11_dirs", lambda names: [v11_dir], raising=False
    )
    directory, source = _locate.resolve_v11_dir(None)
    assert directory == v11_dir
    assert "folder" in source
    # and it is genuinely usable, not merely resolvable
    frame = mc.load_cycle_features(data_dir=exploration_dir)
    assert len(frame) > 0


def test_no_url_is_invented_while_unpublished():
    with pytest.raises(RuntimeError) as excinfo:
        C.v11_url_for(C.V11_INDEX_FILE)
    assert "not published" in str(excinfo.value)


def test_url_for_rejects_a_file_that_is_not_in_the_record():
    with pytest.raises(ValueError):
        C.v11_url_for("analysis_set_cycles.csv")


def test_unpublished_never_touches_the_network(monkeypatch, no_local_v11):
    """The error is raised before any socket call, not after a failed one."""
    import urllib.request

    def explode(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("the loader opened a URL while unpublished")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    with pytest.raises(mc.DataDirError):
        _locate.resolve_v11_dir(None)


def test_no_module_but_constants_hardcodes_the_record():
    """Filling the record in must stay a one-file change.

    Other modules may *read* ``constants.V11_ZENODO_*`` -- that is the point of
    putting them there. What none of them may do is hard-code the record's
    identity: a zenodo.org URL, a DOI or a record id. Those literals belong in
    constants.py and nowhere else.
    """
    import re
    from pathlib import Path

    identity = re.compile(r"zenodo\.org|10\.5281/|/records/\d")
    package = Path(_locate.__file__).resolve().parent
    offenders = []
    for path in sorted(package.glob("*.py")):
        if path.name == "constants.py":
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if identity.search(line):
                offenders.append("{0}:{1}".format(path.name, number))
    assert offenders == [], (
        "these lines hard-code the Zenodo record outside constants.py: "
        "{0}".format(offenders)
    )


def test_constants_is_the_only_place_the_placeholders_are_defined():
    """And the four placeholders are assigned exactly once, in constants.py."""
    import re
    from pathlib import Path

    package = Path(_locate.__file__).resolve().parent
    source = (package / "constants.py").read_text(encoding="utf-8")
    for name in ("V11_ZENODO_DOI", "V11_ZENODO_RECORD_ID", "V11_ZENODO_BASE",
                 "V11_DATA_TAG"):
        assignments = re.findall(
            r"^{0}\s*=".format(name), source, re.MULTILINE
        )
        assert len(assignments) == 1, (name, assignments)


# ---------------------------------------------------------------------------
# the lookup order
# ---------------------------------------------------------------------------

def test_v11_dir_argument_wins(exploration_dir, v11_dir):
    out = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert out.attrs["filters"]["v11_data_dir"] == str(v11_dir)
    assert out.attrs["filters"]["v11_data_source"] == "data_dir= argument"
    assert out.attrs["filters"]["v11_published"] is False


def test_env_var_is_honoured(v11_dir, monkeypatch):
    monkeypatch.setenv(C.DATA_DIR_ENV, str(v11_dir))
    directory, source = _locate.resolve_v11_dir(None)
    assert directory == v11_dir
    assert source == "${0}".format(C.DATA_DIR_ENV)


def test_set_data_dir_is_step_two(v11_dir, monkeypatch):
    monkeypatch.setattr(_locate, "_SESSION_DIR", v11_dir, raising=False)
    directory, source = _locate.resolve_v11_dir(None)
    assert directory == v11_dir
    assert source == "set_data_dir()"


def test_data_dir_is_tried_for_v11_when_it_holds_them(tmp_path, exploration_dir,
                                                      v11_dir):
    """The everything-in-one-folder case needs only data_dir=."""
    both = tmp_path / "both"
    both.mkdir()
    for name in C.REQUIRED_FILES:
        shutil.copy2(exploration_dir / name, both / name)
    for name in C.V11_REQUIRED_FILES:
        shutil.copy2(v11_dir / name, both / name)
    out = mc.load_cycle_features(data_dir=both)
    assert out.attrs["filters"]["v11_data_dir"] == str(both)
    assert out.attrs["filters"]["data_dir"] == str(both)


def test_data_dir_need_not_hold_the_v11_files(exploration_dir, v11_dir):
    """data_dir names the three v1.0 CSVs, as everywhere else in the package; it
    is never *required* to hold the v1.1 ones."""
    out = mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert out.attrs["filters"]["data_dir"] == str(exploration_dir)
    assert out.attrs["filters"]["v11_data_dir"] == str(v11_dir)
    assert out.attrs["filters"]["data_dir"] != out.attrs["filters"]["v11_data_dir"]


def test_a_wrong_v11_dir_raises_rather_than_falling_back(tmp_path, v11_dir):
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "readme.txt").write_text("not the data", encoding="utf-8")
    with pytest.raises(mc.DataDirError):
        mc.load_cycle_features(v11_dir=wrong)


def test_similar_names_are_suggested(tmp_path, v11_dir):
    strange = tmp_path / "strange"
    strange.mkdir()
    shutil.copy2(v11_dir / C.V11_INDEX_FILE,
                 strange / "within_cycle_index (1).csv")
    shutil.copy2(v11_dir / C.V11_CELLS_FILE, strange / C.V11_CELLS_FILE)
    with pytest.raises(mc.DataDirError) as excinfo:
        mc.load_cycle_features(v11_dir=strange)
    message = str(excinfo.value)
    assert "within_cycle_index (1).csv" in message
    assert "rename" in message.lower()


# ---------------------------------------------------------------------------
# integrity
# ---------------------------------------------------------------------------

def test_a_corrupted_v11_file_raises_integrity_error(v11_dir):
    target = v11_dir / C.V11_INDEX_FILE
    text = target.read_text(encoding="utf-8").replace("True", "False", 1)
    target.write_text(text, encoding="utf-8")
    with pytest.raises(mc.IntegrityError) as excinfo:
        mc.load_cycle_features(v11_dir=v11_dir)
    message = str(excinfo.value)
    assert "MANIFEST_v1.1.md" in message
    assert "expected:" in message and "actual:" in message
    assert "byte-reproducible" in message


def test_a_user_folder_is_never_written_to(exploration_dir, v11_dir):
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(v11_dir.iterdir())
    }
    mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    mc.load_cell_features(data_dir=exploration_dir, v11_dir=v11_dir)
    mc.load_conditioning(include_cycle_counts=True,
                         data_dir=exploration_dir, v11_dir=v11_dir)
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(v11_dir.iterdir())
    }
    assert before == after
    assert sorted(before) == sorted(C.V11_REQUIRED_FILES)


def test_hashes_are_checked_once_per_process(exploration_dir, v11_dir, monkeypatch):
    calls = []
    real = _locate._sha256
    monkeypatch.setattr(_locate, "_sha256", lambda p: calls.append(p) or real(p))
    mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    first = len(calls)
    assert first >= len(C.V11_REQUIRED_FILES)
    mc.load_cell_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert len(calls) == first, "the second call re-hashed the v1.1 files"


def test_the_index_is_read_with_usecols_not_whole(exploration_dir, v11_dir,
                                                  monkeypatch):
    """Decision: never materialise the published 72.8 MB index in full."""
    import pandas as pd

    seen = {}
    real = pd.read_csv

    def spy(path, *args, **kwargs):
        if str(path).endswith(C.V11_INDEX_FILE):
            seen["usecols"] = kwargs.get("usecols")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", spy)
    mc.load_cycle_features(data_dir=exploration_dir, v11_dir=v11_dir)
    assert seen.get("usecols") is not None, "the index was read without usecols"
    assert set(seen["usecols"]) == set(C.V11_TABLE_COLUMNS)
    assert len(C.V11_TABLE_COLUMNS) < C.V11_INDEX_N_COLUMNS
