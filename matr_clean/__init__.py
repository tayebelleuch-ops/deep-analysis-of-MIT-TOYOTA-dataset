"""matr_clean -- the cleaned MIT-Stanford-TRI battery dataset, ready to import.

The Severson/Attia fast-charging dataset (Nature Energy, 2019) ships as three
multi-gigabyte MATLAB v7.3 files. This package hands you the audited, documented
**analysis set** derived from them instead: 135 physical cells and 113,559 cycles as
two tidy CSVs, plus the per-cell inventory. It needs pandas and numpy only -- no
h5py, and none of the raw ``.mat`` files.

    >>> import matr_clean as mc
    >>> mc.describe()                      # what the defaults hide, counted live
    >>> labels = mc.load_labels()          # cells with an 80%-SOH cycle life
    >>> cells, cycles = mc.load_trajectories()
    >>> for split in mc.cv_splits("batch"):
    ...     ...

Where the data comes from: an explicit ``data_dir``, then :func:`set_data_dir`, then
``$MATR_CLEAN_DATA_DIR``, then the repository's ``exploration/`` folder if you are in
a clone, and finally a one-off download into ``~/.cache/matr_clean`` from URLs pinned
to the ``v1.0`` tag. Every file is checked against the SHA-256 recorded for that tag
before it is used.

The data is CC BY 4.0 (see ``NOTICE.md`` for the attribution); this code is MIT.
Decisions D0-D5 behind the cleaning are in ``exploration/REPORT.md`` section 6 and are
not re-litigated here. ``USAGE.md`` has worked examples, including Google Colab and
Google Drive.
"""

from __future__ import annotations

from . import constants
from ._locate import (
    DataDirError,
    DownloadError,
    IntegrityError,
    get_data_dir,
    set_data_dir,
)
from .constants import (
    CELLS_FILE,
    CYCLES_FILE,
    DATA_TAG,
    INVENTORY_FILE,
    NOMINAL_CAPACITY_AH,
    REQUIRED_FILES,
    SHA256,
    SOH_THRESHOLD_AH,
)
from .loaders import (
    Trajectories,
    counts,
    describe,
    load_cells,
    load_cycles,
    load_labels,
    load_trajectories,
)
from .splits import Split, cv_splits, split_labels

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # loaders
    "load_cells",
    "load_cycles",
    "load_trajectories",
    "load_labels",
    "cv_splits",
    "describe",
    "counts",
    "set_data_dir",
    "get_data_dir",
    # types
    "Trajectories",
    "Split",
    "split_labels",
    # errors
    "DataDirError",
    "IntegrityError",
    "DownloadError",
    # constants
    "constants",
    "DATA_TAG",
    "REQUIRED_FILES",
    "SHA256",
    "CELLS_FILE",
    "CYCLES_FILE",
    "INVENTORY_FILE",
    "NOMINAL_CAPACITY_AH",
    "SOH_THRESHOLD_AH",
]
