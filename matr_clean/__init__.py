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

As of v0.2.0 the per-cycle *exogenous* variables are here too, read from the v1.1
within-cycle index -- still pandas and numpy only, because that index is a CSV::

    >>> feats = mc.load_cycle_features()   # IR, QCharge, Tavg/Tmax/Tmin, chargetime
    >>> cond = mc.load_conditioning()      # policy numbers aligned to cells

Where the data comes from: an explicit ``data_dir``, then :func:`set_data_dir`, then
``$MATR_CLEAN_DATA_DIR``, then the repository's ``exploration/`` folder if you are in
a clone, and finally a one-off download into ``~/.cache/matr_clean``. The three v1.0
CSVs are pinned to the ``v1.0`` git tag; the v1.1 within-cycle files are pinned to one
published Zenodo *version* record -- ``constants.V11_ZENODO_DOI``, never the concept
DOI -- and only the files a call actually needs are fetched. Every file is checked
against its recorded SHA-256 before it is used.

What is **not** here yet: the nine within-cycle series (``t``, ``I``, ``V``, ``T``,
``Qc``, ``Qd``) and the three interpolated grid curves (``Qdlin``, ``Tdlin``,
``discharge_dQdV``) with their ``Vdlin`` grid. Those live in 2.2 GB of HDF5 and
arrive in v0.3.0 behind an optional ``series`` extra. ``mc.describe()`` lists every
such field and which release carries it.

``is_clean_cycle`` is a summary-level flag about capacity and is **not** safe for
voltage or time-series work. v1.1 adds ``is_series_valid``, computed from each
cycle's own series, which :func:`load_cycle_features` applies by default and
:func:`load_cycles` applies on request. The two disagree in both directions and
neither supersedes the other; no v1.0 file or flag is edited.

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
    resolve_v11_dir,
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
from .features import (
    load_cell_features,
    load_conditioning,
    load_cycle_features,
    v11_counts,
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

__version__ = "0.2.2"

__all__ = [
    "__version__",
    # loaders
    "load_cells",
    "load_cycles",
    "load_trajectories",
    "load_labels",
    # v1.1
    "load_cycle_features",
    "load_cell_features",
    "load_conditioning",
    "v11_counts",
    "cv_splits",
    "describe",
    "counts",
    "set_data_dir",
    "get_data_dir",
    "resolve_v11_dir",
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
