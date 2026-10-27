"""Fixed facts about the analysis set: filenames, pinned URLs, SHA-256, thresholds.

These constants are the package's copy of the provenance record in
``exploration/MANIFEST.md``. They live here because ``MANIFEST.md`` is a repository
document and is **not** installed by ``pip``, so a wheel installed from a tag has no
other way to know what the files it reads are supposed to be.

``tests/test_manifest_hashes.py`` asserts that every value below still equals the
value recorded in ``exploration/MANIFEST.md`` when a clone is available.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The repository the data is published from.
REPO = "tayebelleuch-ops/deep-analysis-of-MIT-TOYOTA-dataset"

#: The git tag the three CSVs are pinned to. Downloads never read a branch, so a
#: later commit on ``main`` can never change what this package loads.
DATA_TAG = "v1.0"

#: Base of the pinned raw-content URLs.
RAW_BASE = "https://raw.githubusercontent.com/{repo}/{tag}/exploration".format(
    repo=REPO, tag=DATA_TAG
)

#: The three files the package needs. Order is load order, not importance.
CELLS_FILE = "analysis_set_cells.csv"
CYCLES_FILE = "analysis_set_cycles.csv"
INVENTORY_FILE = "cell_inventory.csv"

REQUIRED_FILES = (CELLS_FILE, CYCLES_FILE, INVENTORY_FILE)

#: SHA-256 of each required file, as recorded in ``exploration/MANIFEST.md`` for the
#: ``v1.0`` tag. The rebuild documented there is byte-reproducible, so a correctly
#: regenerated file hashes to the same value.
SHA256 = {
    CELLS_FILE: "4608880c9f3e96836685aa56383f26f9a060575a3078756ae2c4c51ba43c470e",
    CYCLES_FILE: "52105f75250a2f6e7acb673a3fa7c04b0e4c3cb6cadedde9fd49972f90e823c1",
    INVENTORY_FILE: "fe3e3115939eb1322acecda81afdf2bec54e505bb43b96a40df6836e6e3514f2",
}

#: Size in bytes of each required file, same source. Used only in error messages.
SIZE_BYTES = {
    CELLS_FILE: 34977,
    CYCLES_FILE: 11244936,
    INVENTORY_FILE: 65050,
}

#: Environment variable checked as step 3 of the lookup order.
DATA_DIR_ENV = "MATR_CLEAN_DATA_DIR"

#: Environment variable that relocates the download cache. Unset, the cache is
#: ``~/.cache/matr_clean``.
CACHE_DIR_ENV = "MATR_CLEAN_CACHE_DIR"

# ---------------------------------------------------------------------------
# Decisions D0-D5, carried here so a user of the loader can read them off the
# package. Full reasoning: exploration/REPORT.md section 6, exploration/cleaning_plan.md.
# ---------------------------------------------------------------------------

#: D0: the SOH denominator is the 1.1 Ah nominal capacity, not each cell's own initial
#: capacity (~1.07 Ah median). "80% SOH" therefore means 0.88 Ah everywhere.
NOMINAL_CAPACITY_AH = 1.1
SOH_THRESHOLD_AH = 0.88

#: The four orthogonal per-cycle quality flags. ``is_clean_cycle`` is their
#: conjunction: measured, and not an artifact, restart or junction cycle.
MEASURED_FLAG = "is_measured_cycle"
REJECT_FLAGS = ("is_artifact_cycle", "is_restart_cycle", "is_junction_cycle")
CLEAN_FLAG = "is_clean_cycle"

#: The fold rule, fixed on 2026-10-27 (exploration/MANIFEST.md, "The split").
SPLIT_SEED = 20261027
N_FOLDS = 5
TEST_FOLD = -1


def cache_dir() -> Path:
    """Return the download cache directory, creating nothing.

    ``~/.cache/matr_clean`` unless ``MATR_CLEAN_CACHE_DIR`` overrides it.
    """
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "matr_clean"


def url_for(filename: str) -> str:
    """Return the pinned raw-content URL for one required file."""
    if filename not in REQUIRED_FILES:
        raise ValueError(
            "{0!r} is not one of the required files: {1}".format(
                filename, ", ".join(REQUIRED_FILES)
            )
        )
    return "{base}/{name}".format(base=RAW_BASE, name=filename)
