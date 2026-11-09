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
#:
#: All four judge a cycle's ``QDischarge`` value against its neighbours, so
#: ``is_clean_cycle`` is a **summary-level** flag. It is not a warrant that the
#: cycle's voltage, current, temperature or time series is usable, and must not be
#: used to select cycles for voltage-domain or time-series work. The v1.1
#: within-cycle extraction adds ``is_series_valid`` for that question; it is not
#: released.
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


# ===========================================================================
# v1.1: the within-cycle extraction
# ===========================================================================
# The v1.1 release adds the six per-cycle summary series v1.0 omits, nine
# series-validity flags and ~45 per-cycle diagnostics, as one CSV index, plus the
# nine within-cycle series as three HDF5 files.
#
# v0.2.0 of this package reads the **index only**, which is why it still needs
# nothing but pandas and numpy. The HDF5 files arrive with v0.3.0 behind the
# optional ``series`` extra.
#
# Provenance: exploration/MANIFEST_v1.1.md. tests/test_manifest_hashes.py asserts
# every value below still equals the value recorded there.

# ---------------------------------------------------------------------------
# The Zenodo record -- THE ONLY PLACE ANYTHING ZENODO-DEPENDENT LIVES
# ---------------------------------------------------------------------------
# The record was published on 2026-11-05. Every value below was read out of the
# record's own files API listing (``GET /api/records/23984188/files``) on
# 2026-11-09 and cross-checked against the local extraction outputs -- none of it
# is a URL pattern typed from memory, because Zenodo serves a file's *bytes* and
# a file's *metadata* from two different paths and only the listing says which is
# which. A published record cannot be edited or deleted, only superseded, so
# these values are stable for as long as the record exists.
#
# Set to ``None`` again (all of V11_ZENODO_BASE / V11_ZENODO_RECORD_ID) and the
# package falls back to its pre-publication behaviour: data_dir=, set_data_dir(),
# $MATR_CLEAN_DATA_DIR and a clone keep working, and every download path raises
# DataDirError with one clear message before any socket call.

#: The *version* DOI, never the concept DOI: a concept DOI resolves to whichever
#: version is latest, which would silently change what this package loads.
V11_ZENODO_DOI = "10.5281/zenodo.23984188"

#: The concept DOI, recorded so a caller can read it off the package. Nothing in
#: the loader resolves it, for the reason given above.
V11_ZENODO_CONCEPT_DOI = "10.5281/zenodo.23984187"

#: The numeric record id of the published version.
V11_ZENODO_RECORD_ID = 23984188

#: The record's files endpoint, exactly as the API reports its own ``links.self``.
#: A file's bytes are at ``{base}/{filename}/content`` (the listing's
#: ``links.content``), which is what :func:`v11_url_for` builds; ``{base}/{filename}``
#: without that suffix returns the file's JSON metadata, not the file.
V11_ZENODO_BASE = "https://zenodo.org/api/records/23984188/files"

#: The human-readable record page (the API's ``links.self_html``). Used only in
#: error messages, where someone is being asked to fetch a file by hand.
V11_ZENODO_RECORD_URL = "https://zenodo.org/records/23984188"

#: Zenodo's own version label for this record, as distinct from the git tag.
V11_ZENODO_VERSION_LABEL = "1.1.0"

#: The git tag the record corresponds to.
V11_DATA_TAG = "v1.1"

# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------

#: The per-cycle index: 114,738 rows x 77 columns. All of v0.2.0 reads this file.
V11_INDEX_FILE = "within_cycle_index.csv"

#: Per-cell metadata absent from analysis_set_cells.csv: 135 rows.
V11_CELLS_FILE = "within_cycle_cells.csv"

#: The two files v0.2.0 needs.
V11_REQUIRED_FILES = (V11_INDEX_FILE, V11_CELLS_FILE)

#: ``source_batch_date`` -> HDF5 filename. Read by v0.3.0, listed here so the
#: hashes and the dispatch rule live in one place.
#:
#: Keyed by ``source_batch_date`` and **never** by ``batch_date``: five cells are
#: continued across batches, and ``batch_date`` in both v1.0 CSVs is the *first*
#: segment's on every row, so it names the wrong file for a segment-2 cycle.
V11_H5_FILES = {
    "2017-05-12": "within_cycle_2017-05-12.h5",
    "2017-06-30": "within_cycle_2017-06-30.h5",
    "2018-04-12": "within_cycle_2018-04-12.h5",
}

#: Everything the published record carries that this package may read.
V11_ALL_DATA_FILES = V11_REQUIRED_FILES + tuple(
    V11_H5_FILES[date] for date in sorted(V11_H5_FILES)
)

# ---------------------------------------------------------------------------
# SHA-256 and sizes, from MANIFEST_v1.1.md
# ---------------------------------------------------------------------------
# These five are final: the extraction is byte-reproducible, so a correctly
# regenerated file hashes to the same value. They were pinned before the record
# was published, because they do not depend on it -- and they are what the loader
# verifies, whether a file came from a clone, a folder or the Zenodo download.
#
# The published record carries three further files that no SHA-256 covers and that
# this package never reads: SHA256SUMS.txt, EXTRACTION.md and LICENSE.txt.
# SHA256SUMS.txt itself covers six files, of which five are published -- it also
# hashes within_cycle_index_raw.csv, the pre-flag intermediate, which is
# deliberately not uploaded. So of the record's 8 files, 5 have published SHA-256
# and 4 are ever loaded. (Zenodo reports an MD5 for all 8; the five that matter
# are in V11_ZENODO_MD5 below.)

V11_SHA256 = {
    "within_cycle_2017-05-12.h5": (
        "8a789f4a83409ad0c1d6c214c836f2de94b63ef2e73a50722fe057c3d8a89d77"
    ),
    "within_cycle_2017-06-30.h5": (
        "5f3f752d9d9a0276442fbb853941d9b212e7fffd152995b207ae6fa4a4503fae"
    ),
    "within_cycle_2018-04-12.h5": (
        "bdd195323719986b3d77d4bd610c26e5e4e7c8d8ddde558b03b4696a2bcc6107"
    ),
    V11_INDEX_FILE: (
        "93176963bbaaaea60a46591a3e7d1e5c3f1a04a250107eec1b754a3311b207dc"
    ),
    V11_CELLS_FILE: (
        "ebdfca86381f7a092da9dcfdb57c90a18c716957fd37080aa8c5cd208ab3147d"
    ),
}

V11_SIZE_BYTES = {
    "within_cycle_2017-05-12.h5": 797659714,
    "within_cycle_2017-06-30.h5": 581592476,
    "within_cycle_2018-04-12.h5": 823392641,
    V11_INDEX_FILE: 72846386,
    V11_CELLS_FILE: 14379,
}

#: MD5 of the same five files, as the Zenodo files API reports them. Recorded
#: because MD5 is the *only* checksum Zenodo publishes, so it is what a reader can
#: compare against the record page without downloading anything, and it is the
#: cross-check that proves the uploaded bytes are the extraction's own: all five
#: were verified against exploration/extract_out/ on 2026-11-09. The loader itself
#: verifies SHA-256 and never MD5 -- these are provenance, not a code path.
V11_ZENODO_MD5 = {
    "within_cycle_2017-05-12.h5": "139cd63ebae1f8c7939dfc205e60932b",
    "within_cycle_2017-06-30.h5": "667b381648fa7ac4ea9f17c6c76f98a9",
    "within_cycle_2018-04-12.h5": "995124d8268c80f476a2d19ce29cb067",
    V11_INDEX_FILE: "a6bbaea97eedd3f0a1158dc49e75e771",
    V11_CELLS_FILE: "97df74cb201efc8efda7da5dc6925560",
}

#: Total bytes of HDF5, for the messages that warn about the download size.
V11_H5_TOTAL_BYTES = sum(
    V11_SIZE_BYTES[name] for name in V11_H5_FILES.values()
)

# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

#: Width of the published index. v0.2.0 reads the subset below with ``usecols``,
#: so the full 72.8 MB is never materialised; the other ~48 columns are per-cycle
#: diagnostics, documented in exploration/EXTRACTION.md section 4 and readable
#: straight from the file.
V11_INDEX_N_COLUMNS = 77

#: Keys and provenance. ``source_struct_index`` is kept because it is the evidence
#: that addressing is not positional: it differs from ``source_channel - 1`` for
#: 113 of the 140 struct rows.
V11_KEY_COLUMNS = (
    "cell_uid",
    "cycle",
    "segment",
    "source_batch_date",
    "source_channel",
    "source_struct_index",
    "h5_row",
    "n_samples",
    "grid_len_raw",
)

#: The four status flags.
V11_STATUS_FLAGS = (
    "in_analysis_set",
    "beyond_crossing",
    "is_placeholder",
    "is_series_valid",
)

#: The nine checks whose conjunction is ``is_series_valid``. Each asks one question
#: about one cycle's own series; none uses a window over neighbouring cycles, which
#: is what makes them independent of the v1.0 summary-level flags.
V11_COMPONENT_FLAGS = (
    "series_present",
    "series_time_monotone",
    "series_time_contiguous",
    "series_duration_plausible",
    "series_length_plausible",
    "series_voltage_in_range",
    "series_current_in_range",
    "series_grid_in_range",
    "series_no_nan",
)

#: The six per-cycle summary series that none of the three v1.0 CSVs carries,
#: plus ``QDischarge_Ah``, which they do -- it is carried here as the join proof
#: and is bit-for-bit equal to ``QD_Ah`` on all 113,559 shared rows.
V11_SERIES_COLUMNS = (
    "QDischarge_Ah",
    "QCharge_Ah",
    "IR_ohm",
    "Tavg_C",
    "Tmax_C",
    "Tmin_C",
    "chargetime_min",
)

#: The six of those that are genuinely new in v1.1.
V11_NEW_SERIES_COLUMNS = tuple(
    name for name in V11_SERIES_COLUMNS if name != "QDischarge_Ah"
)

#: What ``load_cycle_features`` reads from the index, in output order.
V11_TABLE_COLUMNS = (
    V11_KEY_COLUMNS + V11_STATUS_FLAGS + V11_COMPONENT_FLAGS + V11_SERIES_COLUMNS
)

#: The six columns ``within_cycle_cells.csv`` adds to ``analysis_set_cells.csv``.
V11_CELL_COLUMNS = (
    "n_segments",
    "segments_resolved",
    "n_cycles_total",
    "policy_underscore",
    "policy_readable_as_stored",
    "cycle_life_struct_field",
)

#: The v1.1 per-cycle flag, named so a caller can read it off the package rather
#: than typing the string. Its nine components are :data:`V11_COMPONENT_FLAGS`.
#:
#: ``is_series_valid`` is **not** a replacement for ``is_clean_cycle`` and neither
#: supersedes the other: ``is_clean_cycle`` judges a cycle's QDischarge against its
#: neighbours (an 11-cycle rolling median), ``is_series_valid`` judges the integrity
#: of the cycle's own trace. On the 113,559 analysis-set rows they disagree both
#: ways -- 171 rows are clean but series-invalid, 87 the reverse. The 171 proposed
#: corrections in exploration/tables/v11_proposed_clean_cycle_corrections.csv are
#: **not applied** to any v1.0 file and the v1.0 hashes above stay pinned.
V11_SERIES_FLAG = "is_series_valid"

#: The four per-cell quality flags :func:`matr_clean.load_series` returns aligned to
#: ``cell_uid``, all read from ``analysis_set_cells.csv`` and returned **as stored**.
#: They are per-cell judgements and are deliberately not folded into the per-cycle
#: mask: a thermocouple fault is a reason to distrust a cell's temperature, not a
#: reason to drop its voltage.
V11_CELL_FLAGS = (
    "is_continuation",
    "has_eol_label",
    "thermocouple_fault",
    "exclude_from_deltaq_features",
)

#: The three interpolated grid fields, on the :data:`V11_VDLIN_POINTS`-point grid.
#: Read by :func:`matr_clean.load_series`; ``discharge_dQdV`` is the dataset's own
#: name -- ``dQdV`` is an index column name and is not a field.
V11_GRID_FIELDS = ("Qdlin", "Tdlin", "discharge_dQdV")

#: The six native (ragged) within-cycle series, plus the time base.
V11_NATIVE_FIELDS = ("t", "I", "V", "T", "Qc", "Qd")

#: The voltage grid: 1000 points, 3.5 V -> 2.0 V. Stored in every HDF5 file as
#: ``/vdlin`` and returned as stored, never reconstructed -- it is equal to
#: ``np.linspace(3.5, 2.0, 1000)`` to one ulp but not bitwise (15 of 1000 points
#: differ, by <= 4.44e-16).
V11_VDLIN_POINTS = 1000
V11_VDLIN_START_V = 3.5
V11_VDLIN_STOP_V = 2.0

#: Published row counts, asserted by tests/test_v11_counts.py against the data.
V11_STRUCT_CYCLES = 114738
V11_ANALYSIS_CYCLES = 113559
V11_BEYOND_CROSSING = 1179
V11_PLACEHOLDERS = 46
V11_CELLS = 135
V11_STRUCT_ROWS = 140

#: ``is_series_valid`` is False on this many cycles, across this many cells. The
#: 48/32/34 triple quoted in REPORT_v1.1.md is the ``series_grid_in_range``
#: component alone, not the total -- see V11_GRID_RANGE_* below.
V11_SERIES_INVALID_CYCLES = 249
V11_SERIES_INVALID_CELLS = 97

#: The impossible interpolated values (finding U13): Qdlin outside
#: [-0.10, 1.50] Ah, Tdlin outside [0, 80] degC or dQdV outside [-200, 0] Ah/V.
#: Extremes reach +1430.7 Ah and -4030.3 Ah on a 1.1 Ah cell.
V11_GRID_RANGE_CYCLES = 48
V11_GRID_RANGE_CELLS = 32
V11_GRID_RANGE_CLEAN_IN_V1_0 = 34

#: The two flags' disagreement on the 113,559 analysis-set rows.
V11_DISPUTED_CYCLES = 171      # is_clean_cycle True, is_series_valid False
V11_DISPUTED_CELLS = 54
V11_REVERSE_CYCLES = 87        # is_clean_cycle False, is_series_valid True
V11_BOTH_INVALID_CYCLES = 78
V11_BOTH_VALID_CYCLES = 113223

#: The five cells continued across batches. Their segment-2 cycles live in
#: ``within_cycle_2017-06-30.h5`` while their ``batch_date`` says ``2017-05-12``.
#: tests/test_v11_continuation.py asserts the dispatch uses source_batch_date.
V11_CONTINUATION_CELLS = (
    "EL150800460486",
    "EL150800460514",
    "EL150800460623",
    "EL150800464865",
    "EL150800464977",
)


def v11_url_for(filename: str) -> str:
    """Return the pinned Zenodo download URL for one v1.1 file.

    The shape is the files API's own ``links.content`` -- ``{base}/{name}/content``
    -- not ``{base}/{name}``, which serves that file's JSON metadata instead of its
    bytes. Both are pinned to the *version* record, so the bytes this returns cannot
    change under a caller.

    Raises :class:`RuntimeError` if the record constants have been blanked, because
    there is then no honest URL to return. Callers that want the
    published/unpublished answer without an exception should test
    :func:`v11_is_published`.
    """
    if filename not in V11_SHA256:
        raise ValueError(
            "{0!r} is not a v1.1 data file: {1}".format(
                filename, ", ".join(sorted(V11_SHA256))
            )
        )
    if not v11_is_published():
        raise RuntimeError(
            "the v1.1 Zenodo record is not published, so {0} has no URL yet"
            .format(filename)
        )
    return "{base}/{name}/content".format(base=V11_ZENODO_BASE, name=filename)


def v11_is_published() -> bool:
    """True once the Zenodo placeholders in this module have been filled in."""
    return bool(V11_ZENODO_BASE) and bool(V11_ZENODO_RECORD_ID)
