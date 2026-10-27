"""Read-only lazy accessor for the MATR / Severson et al. v7.3 .mat batch structs.

Why this exists rather than reusing `eda_utils.py` / the `Data/*.pkl` files:

* `build_pkl.py` does not capture `barcode` or `channel_id`, and upstream's README
  says they are "not available in the pkl files". They ARE in the .mat files, but
  as MATLAB `string` objects, which h5py cannot decode directly -- see
  `decode_mcos_string` below. Step 1's inventory is keyed on channel + barcode, so
  this module reads the .mat files directly.
* The pickles are 2-3 GB each and loading all three at once OOM-kills a 19 GB box
  (hence `eda_utils_v2._strip_cycles`). Reading the .mat lazily through h5py lets us
  pull exactly the cycles we need for the voltage-domain plots and nothing more.

Nothing here writes to the data files; every handle is opened mode="r".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

REPO = Path(__file__).resolve().parent.parent

# Batch date -> raw struct path. These are the three batches of the published
# 124-cell dataset; Data/ also holds a 2019-01-24 file and `dataset batteries/`
# holds 2018-02-20 + 2018-04-03, which are NOT part of this dataset.
BATCH_FILES = {
    "2017-05-12": REPO / "Data" / "2017-05-12_batchdata_updated_struct_errorcorrect.mat",
    "2017-06-30": REPO / "Data" / "2017-06-30_batchdata_updated_struct_errorcorrect.mat",
    "2018-04-12": REPO / "Data" / "2018-04-12_batchdata_updated_struct_errorcorrect.mat",
}
BATCH_DATES = list(BATCH_FILES)

# Nominal cell spec (page 01): A123 APR18650M1A, 1.1 Ah nominal, 3.3 V nominal.
NOMINAL_CAPACITY_AH = 1.1
# Published end-of-life threshold named on all three batch pages: 0.88 Ah,
# which is 80% of the 1.1 Ah nominal capacity.
EOL_THRESHOLD_AH = 0.88
# 75% of nominal. Page 03 (2017-06-30) says "75% of nominal capacity (0.88 Ah)",
# two mutually inconsistent figures; 2017-06-30's cells actually stop at
# ~0.825 Ah, so the percentage is the correct half of that sentence.
EOL_75PCT_AH = 0.75 * NOMINAL_CAPACITY_AH
# A cell whose last recorded discharge capacity is at or below this counts as
# having reached its test's termination criterion rather than being censored.
# Chosen to sit in the empty gap in the observed QD_last distribution: cells
# that terminated at criterion end at 0.8800-0.8834 Ah, the genuinely
# unfinished ones at 0.9131 Ah and above.
CRITERION_REACHED_MAX_AH = 0.89

SUMMARY_FIELDS = ("IR", "QCharge", "QDischarge", "Tavg", "Tmax", "Tmin",
                  "chargetime", "cycle")
CYCLE_FIELDS = ("I", "Qc", "Qd", "Qdlin", "T", "Tdlin", "V", "discharge_dQdV", "t")

# Colorblind-safe categorical slots (blue / orange / aqua) held fixed for batch
# identity in every figure, matching eda_utils.BATCH_COLORS.
BATCH_COLORS = {"2017-05-12": "#2a78d6", "2017-06-30": "#eb6834", "2018-04-12": "#1baf7a"}


# --------------------------------------------------------------------------
# string decoding
# --------------------------------------------------------------------------

def decode_char(f: h5py.File, ref) -> str:
    """Decode a MATLAB `char` array (policy, policy_readable, batch_date)."""
    return np.ravel(f[ref][()]).astype(np.uint16).tobytes().decode("utf-16-le")


def _unpack_mcos_string(words: np.ndarray) -> str:
    """Unpack MATLAB's `string`-class payload: a uint64 vector laid out as
    [version, ndims, dim1, dim2, nchar, <UTF-16 chars packed 4 per uint64>].
    """
    words = np.ravel(np.asarray(words, dtype=np.uint64))
    nchar = int(words[4])
    if nchar == 0:
        return ""
    chars = words[5:].view(np.uint16)[:nchar]
    return chars.tobytes().decode("utf-16-le")


def decode_mcos_string(f: h5py.File, ref) -> str:
    """Decode a MATLAB `string` object reference (barcode, channel_id).

    These are stored as opaque MCOS objects: the dataset at `ref` holds
    [0xdd000000, ndims, dim1, dim2, object_id, class_id], and the payload lives in
    `/#subsystem#/MCOS`, whose element 0 is the class-metadata blob and whose
    element i holds object id i-1. Verified empirically on 2017-05-12: object ids
    47 and 92 decode to channels "1" and "48", and ids 1..46 to 14-character
    EL-prefixed barcodes.
    """
    payload = np.ravel(f[ref][()]).astype(np.uint64)
    object_id = int(payload[4])
    mcos = f["#subsystem#"]["MCOS"]
    entry = f[mcos[0, object_id + 1]][()]
    return _unpack_mcos_string(entry)


def _summary_array(group: h5py.Group, f: h5py.File, key: str) -> np.ndarray:
    """Read one summary field as a 1-D float array, tolerating both the
    plain (1, N) float layout and a (1, N) reference layout."""
    ds = group[key]
    if ds.dtype == object:
        return np.hstack([np.ravel(f[r][()]) for r in np.ravel(ds[()])]).astype(float)
    return np.ravel(ds[()]).astype(float)


# --------------------------------------------------------------------------
# per-cell metadata
# --------------------------------------------------------------------------

@dataclass
class CellRecord:
    batch_date: str
    index: int                 # position within the batch struct (0-based)
    barcode: str
    channel: int
    policy: str                # raw underscore form, e.g. "3_6C-80PER_3_6C"
    policy_readable: str       # e.g. "3.6C(80%)-3.6C"
    cycle_life_field: float    # the struct's own cycle_life value
    n_cycles: int              # number of entries in the `cycles` group
    summary: dict = field(default_factory=dict)

    @property
    def cell_id(self) -> str:
        return f"{self.batch_date}:ch{self.channel:02d}"


def read_batch_metadata(batch_date: str, path: Path | None = None) -> list[CellRecord]:
    """All descriptors + the full `summary` block for every cell in one batch.

    Reads no per-cycle arrays, so this is cheap (seconds, tens of MB) even though
    the files are 2-3 GB.
    """
    path = Path(path) if path else BATCH_FILES[batch_date]
    out = []
    with h5py.File(path, "r") as f:
        batch = f["batch"]
        file_date = decode_char(f, None) if False else np.ravel(f["batch_date"][()]).astype(np.uint16).tobytes().decode("utf-16-le")
        n = batch["summary"].shape[0]
        for i in range(n):
            summary_group = f[batch["summary"][i, 0]]
            summary = {k: _summary_array(summary_group, f, k) for k in SUMMARY_FIELDS}
            channel_str = decode_mcos_string(f, batch["channel_id"][i, 0])
            out.append(CellRecord(
                batch_date=file_date,
                index=i,
                barcode=decode_mcos_string(f, batch["barcode"][i, 0]),
                channel=int(channel_str),
                policy=decode_char(f, batch["policy"][i, 0]),
                policy_readable=decode_char(f, batch["policy_readable"][i, 0]),
                cycle_life_field=float(np.ravel(f[batch["cycle_life"][i, 0]][()])[0]),
                n_cycles=f[batch["cycles"][i, 0]]["I"].shape[0],
                summary=summary,
            ))
    return out


def read_all_metadata() -> dict[str, list[CellRecord]]:
    return {d: read_batch_metadata(d) for d in BATCH_DATES}


# --------------------------------------------------------------------------
# lazy per-cycle access
# --------------------------------------------------------------------------

class BatchCycles:
    """Context manager for pulling individual cycles out of one batch file.

    >>> with BatchCycles("2018-04-12") as bc:
    ...     qd = bc.cycle(cell_index=0, cycle_index=10, fields=("Qdlin",))
    """

    def __init__(self, batch_date: str, path: Path | None = None):
        self.batch_date = batch_date
        self.path = Path(path) if path else BATCH_FILES[batch_date]
        self._f = None

    def __enter__(self):
        self._f = h5py.File(self.path, "r")
        return self

    def __exit__(self, *exc):
        self._f.close()
        self._f = None
        return False

    @property
    def n_cells(self) -> int:
        return self._f["batch"]["summary"].shape[0]

    def vdlin(self, cell_index: int = 0) -> np.ndarray:
        """The voltage grid Qdlin / Tdlin / discharge_dQdV are interpolated onto."""
        return np.ravel(self._f[self._f["batch"]["Vdlin"][cell_index, 0]][()]).astype(float)

    def n_cycles(self, cell_index: int) -> int:
        return self._f[self._f["batch"]["cycles"][cell_index, 0]]["I"].shape[0]

    def cycle(self, cell_index: int, cycle_index: int,
              fields: tuple[str, ...] = CYCLE_FIELDS) -> dict[str, np.ndarray]:
        """One cycle's within-cycle arrays. `cycle_index` is 0-based into the
        `cycles` group (see exploration/schema.md on how that relates to the
        printed cycle number)."""
        cycles = self._f[self._f["batch"]["cycles"][cell_index, 0]]
        return {k: np.ravel(self._f[cycles[k][cycle_index, 0]][()]).astype(float)
                for k in fields}


# --------------------------------------------------------------------------
# policy parsing
# --------------------------------------------------------------------------

_POLICY_RE = re.compile(
    r"^(?P<c1>\d+(?:\.\d+)?)C\((?P<q1>\d+(?:\.\d+)?)%\)"
    r"(?:-(?P<c2>\d+(?:\.\d+)?)(?P<c2c>C?))?$")

# 2018-04-12 appends this to every policy string; it is a note about the test
# script, not part of the policy, so it is split off rather than left to make
# every 2018 policy look distinct from its 2017 equivalent.
KNOWN_SUFFIXES = ("-newstructure",)


def parse_policy(policy_readable: str) -> dict:
    """Split a `C1(Q1)-C2` policy string into its numeric parts.

    Returns C1, Q1, C2, a `canonical` "C1(Q1)-C2" rendering, any recognised
    trailing `suffix`, and two flags describing how trustworthy the stored
    string is. Nothing is repaired: a string that does not parse is reported
    with parsed=False and `canonical` falling back to the raw text, because two
    distinct corruptions exist in these files and both need to stay visible:

    * 2017-06-30 stores the five continued cells' policies with the leading
      current chopped off -- "80%)-3.6C" for what 2017-05-12 calls
      "3.6C(80%)-3.6C". `truncated_head` marks these.
    * 2017-06-30 ch 30 stores "4C(31%)-5", with the second step's trailing "C"
      missing. `truncated_tail` marks these; C2 is still read as 5.0 since the
      number itself is intact, but the flag says the string was malformed.
    """
    raw = policy_readable.strip()
    body, suffix = raw, ""
    for suf in KNOWN_SUFFIXES:
        if body.endswith(suf):
            body, suffix = body[: -len(suf)], suf
            break

    m = _POLICY_RE.match(body)
    if not m:
        return {"C1": np.nan, "Q1": np.nan, "C2": np.nan, "suffix": suffix,
                "canonical": raw, "parsed": False, "n_steps": np.nan,
                "truncated_head": body.count("(") < body.count(")"),
                "truncated_tail": False}

    c1, q1 = float(m.group("c1")), float(m.group("q1"))
    c2 = float(m.group("c2")) if m.group("c2") else np.nan
    truncated_tail = bool(m.group("c2")) and not m.group("c2c")
    canonical = f"{m.group('c1')}C({m.group('q1')}%)"
    if m.group("c2"):
        canonical += f"-{m.group('c2')}C"
    return {"C1": c1, "Q1": q1, "C2": c2, "suffix": suffix,
            "canonical": canonical, "parsed": True,
            "n_steps": 1 if np.isnan(c2) else 2,
            "truncated_head": False, "truncated_tail": truncated_tail}
