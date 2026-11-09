"""The hashes in matr_clean.constants must equal those in exploration/MANIFEST.md.

MANIFEST.md is a repository document and is not installed by pip, which is why the
package carries its own copy. This test is what keeps the copy honest.
"""

from __future__ import annotations

import hashlib
import re

from matr_clean import constants as C


def _manifest_rows(repo_root):
    """Parse the generated-outputs table: filename -> (rows, bytes, sha256)."""
    text = (repo_root / "exploration" / "MANIFEST.md").read_text(encoding="utf-8")
    rows = {}
    pattern = re.compile(
        r"^\|\s*`exploration/([^`]+)`\s*\|"      # file
        r"\s*([^|]+?)\s*\|"                      # rows
        r"\s*([\d,]+)\s*\|"                      # bytes
        r"\s*`([0-9a-f]{64})`\s*\|\s*$",         # sha256
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        rows[match.group(1)] = {
            "rows": match.group(2),
            "bytes": int(match.group(3).replace(",", "")),
            "sha256": match.group(4),
        }
    return rows


def test_manifest_records_all_three_required_files(repo_root):
    rows = _manifest_rows(repo_root)
    for name in C.REQUIRED_FILES:
        assert name in rows, "{0} is not in MANIFEST.md".format(name)


def test_constant_hashes_equal_the_manifest(repo_root):
    rows = _manifest_rows(repo_root)
    for name in C.REQUIRED_FILES:
        assert C.SHA256[name] == rows[name]["sha256"], (
            "matr_clean.constants.SHA256[{0!r}] has drifted from MANIFEST.md".format(name)
        )


def test_constant_sizes_equal_the_manifest(repo_root):
    rows = _manifest_rows(repo_root)
    for name in C.REQUIRED_FILES:
        assert C.SIZE_BYTES[name] == rows[name]["bytes"]


def test_the_files_in_this_clone_match_the_constants(exploration_dir):
    for name in C.REQUIRED_FILES:
        path = exploration_dir / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == C.SHA256[name]
        assert path.stat().st_size == C.SIZE_BYTES[name]


def test_urls_are_pinned_to_a_tag_not_a_branch():
    assert C.DATA_TAG == "v1.0"
    for name in C.REQUIRED_FILES:
        url = C.url_for(name)
        assert "/v1.0/" in url
        assert "/main/" not in url
        assert url.startswith("https://raw.githubusercontent.com/")


# ---------------------------------------------------------------------------
# v1.1
# ---------------------------------------------------------------------------
# MANIFEST_v1.1.md lives on the within-cycle-extraction branch and arrives on main
# when that branch is merged. Until then these skip, which is why the hashes are
# also asserted against the real files by tests/test_v11_integration.py.

V11_MANIFEST = "MANIFEST_v1.1.md"

#: The Outputs table of MANIFEST_v1.1.md: | `name` | bytes | `sha256` |
_V11_ROW = re.compile(
    r"^\|\s*`([A-Za-z0-9_.\-]+)`\s*\|"      # bare filename, no path prefix
    r"\s*([\d,]+)\s*\|"                      # bytes
    r"\s*`([0-9a-f]{64})`\s*\|\s*$",         # sha256
    re.MULTILINE,
)


def _v11_manifest_rows(repo_root):
    path = repo_root / "exploration" / V11_MANIFEST
    if not path.is_file():
        import pytest

        pytest.skip(
            "{0} is not on this branch yet; it arrives with the "
            "within-cycle-extraction merge. The same hashes are asserted against "
            "the real files by test_v11_integration.py.".format(V11_MANIFEST)
        )
    text = path.read_text(encoding="utf-8")
    return {
        match.group(1): {
            "bytes": int(match.group(2).replace(",", "")),
            "sha256": match.group(3),
        }
        for match in _V11_ROW.finditer(text)
    }


def test_v11_manifest_records_every_file_the_loader_reads(repo_root):
    rows = _v11_manifest_rows(repo_root)
    for name in C.V11_SHA256:
        assert name in rows, "{0} is not in {1}".format(name, V11_MANIFEST)


def test_v11_constant_hashes_equal_the_manifest(repo_root):
    rows = _v11_manifest_rows(repo_root)
    for name, expected in C.V11_SHA256.items():
        assert expected == rows[name]["sha256"], (
            "matr_clean.constants.V11_SHA256[{0!r}] has drifted from {1}".format(
                name, V11_MANIFEST
            )
        )


def test_v11_constant_sizes_equal_the_manifest(repo_root):
    rows = _v11_manifest_rows(repo_root)
    for name, expected in C.V11_SIZE_BYTES.items():
        assert expected == rows[name]["bytes"], name


def test_the_manifest_lists_no_loadable_file_the_constants_omit(repo_root):
    """A newly published data file must not be silently ignored by the loader."""
    rows = _v11_manifest_rows(repo_root)
    loadable = {
        name for name in rows
        if name.endswith(".h5") or name.startswith("within_cycle_")
    }
    # within_cycle_index_raw.csv is the pre-flag intermediate: hashed in the
    # manifest so the pipeline can be audited, deliberately never published and
    # never read. Everything else in that set must be a constant.
    loadable.discard("within_cycle_index_raw.csv")
    missing = sorted(loadable - set(C.V11_SHA256))
    assert missing == [], (
        "{0} lists {1}, which matr_clean.constants.V11_SHA256 does not "
        "cover".format(V11_MANIFEST, missing)
    )


def test_the_v11_hash_table_covers_what_exists_and_says_what_it_does_not():
    """Of the Zenodo record's 8 files, 5 have published hashes and 4 are loaded.

    SHA256SUMS.txt covers six files, of which five are published: it also hashes
    within_cycle_index_raw.csv, which is not uploaded, and it does not hash
    itself, EXTRACTION.md or LICENSE.txt. The constants must not pretend
    otherwise.
    """
    assert len(C.V11_SHA256) == 5
    assert len(C.V11_SIZE_BYTES) == 5
    assert set(C.V11_SHA256) == set(C.V11_SIZE_BYTES)
    # the four the loader ever opens
    assert len(C.V11_ALL_DATA_FILES) == 5
    loaded = set(C.V11_REQUIRED_FILES) | set(C.V11_H5_FILES.values())
    assert loaded == set(C.V11_SHA256)
    # nothing unhashed is claimed as loadable
    for name in ("SHA256SUMS.txt", "EXTRACTION.md", "LICENSE.txt",
                 "within_cycle_index_raw.csv"):
        assert name not in C.V11_SHA256
        assert name not in C.V11_ALL_DATA_FILES


def test_the_v11_urls_are_pinned_to_one_version_of_the_record():
    """The v1.0 counterpart above pins a git tag; this pins a Zenodo version.

    Both say the same thing: a download must not be able to return different bytes
    later. For Zenodo that means the version record, never the concept record and
    never ``/latest``.
    """
    assert C.v11_is_published() is True
    assert C.V11_DATA_TAG == "v1.1"
    for name in C.V11_SHA256:
        url = C.v11_url_for(name)
        assert url.startswith("https://zenodo.org/api/records/23984188/files/")
        assert url.endswith("/content")
        assert "/latest" not in url
        assert "23984187" not in url          # the concept record


def test_the_md5_table_covers_the_same_five_files(repo_root):
    """Zenodo publishes MD5 only, so it is the checksum a reader can compare
    against the record page. It must not drift out of step with the SHA-256
    table, and it must name no file the loader does not know."""
    assert set(C.V11_ZENODO_MD5) == set(C.V11_SHA256)
    for name, value in C.V11_ZENODO_MD5.items():
        assert re.match(r"^[0-9a-f]{32}$", value), name


def test_the_md5_table_matches_the_files_in_this_clone(repo_root):
    """The cross-check that proves the uploaded bytes are the extraction's own.

    Skips the three .h5 files unless they are present: they are 2.20 GB and
    exploration/extract_out/ is gitignored, so a fresh clone has neither.
    """
    import pytest

    extract_out = repo_root / "exploration" / "extract_out"
    checked = 0
    for name, expected in sorted(C.V11_ZENODO_MD5.items()):
        path = extract_out / name
        if not path.is_file():
            continue
        digest = hashlib.md5()
        with open(str(path), "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        assert digest.hexdigest() == expected, name
        checked += 1
    if checked == 0:
        pytest.skip(
            "exploration/extract_out/ holds none of the v1.1 outputs; they are "
            "gitignored and rebuilt by exploration/extract_within_cycle.py"
        )


def test_the_v1_0_hashes_are_unchanged_by_v0_2_0():
    """Decision: v1.0 files are never edited and their hashes stay pinned, so the
    171 proposed is_clean_cycle corrections cannot have been applied."""
    assert C.SHA256[C.CELLS_FILE] == (
        "4608880c9f3e96836685aa56383f26f9a060575a3078756ae2c4c51ba43c470e"
    )
    assert C.SHA256[C.CYCLES_FILE] == (
        "52105f75250a2f6e7acb673a3fa7c04b0e4c3cb6cadedde9fd49972f90e823c1"
    )
    assert C.SHA256[C.INVENTORY_FILE] == (
        "fe3e3115939eb1322acecda81afdf2bec54e505bb43b96a40df6836e6e3514f2"
    )
