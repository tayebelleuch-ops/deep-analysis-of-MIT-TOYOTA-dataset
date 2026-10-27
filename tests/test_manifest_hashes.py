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
