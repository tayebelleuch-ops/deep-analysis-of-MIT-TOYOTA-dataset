# matr_clean v0.3.0 — the HDF5 within-cycle gateway

**Status: plan only. Nothing built, nothing pushed, nothing tagged. `main` is untouched
at `2d2fae7` (`loader-v0.2.2`); this file is the only change on `loader-v0.3-plan`.**

This supersedes **§3, §5, §6 and §7 of `SPEC_v0.2.md`** for everything that touches the
three HDF5 files. `SPEC_v0.2.md` is not edited: its §0–§2 correctly describe the CSV half,
which shipped as 0.2.2, and its §3 was written before 0.2.2 existed and before the Zenodo
record was published. §1 below lists every place it is now wrong.

Verification environment: `/home/tayeb/dev/dscv/ahmed/matr/.venv` — Python 3.13.5,
pandas 3.0.6, numpy 2.5.4, h5py 3.16.0 (HDF5 2.0.0). Every HDF5 file was opened
`mode="r"`; nothing in `exploration/extract_out/` was written, renamed or deleted, and no
mtime moved. The Zenodo record was read once (`GET /api/records/23984188/files`) and
nothing was uploaded.

---

## 0. What changes, in one paragraph

0.2.2 already serves the per-cycle table, the per-cell table and the policy conditioning
from the two published CSVs, and `_locate.resolve_v11_dir(names=…)` already resolves,
verifies and lazily downloads **named files one at a time**. So v0.3.0 adds no download
code and no new data file. It adds exactly two modules — `series.py` and `_h5.py` — whose
job is to turn a `(cell, cycle-range, field-list)` request into array reads against the
three HDF5 files, with the invalid and placeholder cycles **masked in place**. The one
genuinely new design commitment is that **`load_series` is the gateway and
`load_early_window` is a wrapper over it**, inverting `SPEC_v0.2.md` §3, which specified
the window first and the general reader as an afterthought.

---

## 1. Corrections to `SPEC_v0.2.md` §3 (and the HDF5 claims it rests on)

Re-verified against `exploration/extract_out/` and `exploration/MANIFEST_v1.1.md`.
Confirmations are in §1.20; everything before it is a defect.

### 1.1 The module layout never existed

§3 lists `conditioning.py` holding `load_conditioning`. Shipped 0.2.2 has **no
`conditioning.py`**: `load_cycle_features`, `load_cell_features` and `load_conditioning`
all live in `features.py`, together with `series_valid_keys`, `v11_counts` and the
`_V11_CACHE`. `series.py` and `_h5.py` must sit beside `features.py` and reuse its
`_read_v11` / `_resolve_v11`, not beside a module that was never written.

### 1.2 The tri-state `clean=` was rejected during 0.2.0 and must not come back

§1.6, §1.7 and every signature in §3 are built on `clean="series" | "summary" | False`.
Shipped 0.2.2 does not have it. The real signature is

```python
load_cycle_features(variables=None, clean=True, require_series_valid=True,
                    beyond_crossing=False, include_test=False,
                    data_dir=None, v11_dir=None)
```

— **two independent booleans**, `clean` (v1.0 `is_clean_cycle`) and
`require_series_valid` (v1.1 `is_series_valid`), because the two flags judge different
things and neither supersedes the other (`MANIFEST_v1.1.md`, Detector cutoffs). v0.3.0
must take the same two booleans. Introducing a tri-state now would make
`load_series(clean="series")` and `load_cycle_features(clean=True)` mean different things
under one keyword — the exact collision §1.7 was written to avoid.

Consequence: §1.6's "resolution" ("`clean` drops rows in DataFrame returns and sets the
mask in array returns") is obsolete as written. The surviving rule, restated in §2.6, is
about *which predicate* masks, not about one keyword doing two jobs.

### 1.3 `v11_dir=` is missing from every signature in §3

Every v1.1 function in 0.2.2 takes **both** `data_dir=` (the v1.0 CSVs) and `v11_dir=`
(the v1.1 files), because a user can plausibly have the 11 MB of v1.0 CSVs in a clone and
the 2.2 GB of HDF5 on an external disk or a Kaggle mount. §3 shows only `data_dir=`. All
four new functions must take both.

### 1.4 `dQdV` is not a field name

§3's `fields=("Qdlin","Tdlin","dQdV")` names a dataset that does not exist. The HDF5
dataset, the index columns and `constants.V11_GRID_FIELDS` all say **`discharge_dQdV`**.
(`dQdV_min` / `dQdV_max` are index *column* names; the field is not.)

### 1.5 `load_series(..., grid=False)` cannot express the request the team actually makes

A boolean `grid=` partitions the fields into "all native" or "all grid". It cannot ask
for `V` and `Qdlin` in one call, which is what anyone comparing a raw trace against its
interpolation does. Replaced in §2.1 by a single `fields=` tuple drawn from
`V11_NATIVE_FIELDS + V11_GRID_FIELDS`, with the return type determined per field.

### 1.6 The default native field list drops two of the six

§3's `fields=("t","I","V","T")` omits `Qc` and `Qd`. `constants.V11_NATIVE_FIELDS` is
`("t","I","V","T","Qc","Qd")`. For the stated use case the default should be the three
**grid** fields anyway (§2.1), since those are the model input.

### 1.7 "~60 MB for the largest cell" is low

Measured on the largest cell, `EL150800460623` (2,236 cycles, 2,370,992 native samples,
spanning two files):

| request | payload |
|---|---|
| all six native fields | 63.3 MiB |
| all six native + all three grid | **88.9 MiB** |

§3's 60 MB covers the native case only. §2.4 gives the figure with process RSS attached.

### 1.8 The dtype table (§1.4) is right but incomplete in five ways

Re-read from all three files. The table itself verifies exactly. What a reader also needs
and §1.4 does not say:

* **The root group carries no attributes at all.** `f.attrs == {}` in all three files. §5's
  fixture instruction "the same attributes" has nothing to copy at the root; the attributes
  that exist are per-dataset (`units` on all seven payload datasets, `grid`+`note` on the
  three grids, `note` on `native/offset` and on `vdlin`).
* **Only the seven payload datasets are chunked.** `native/{I,V,T,Qc,Qd,t}` and
  `grid/{Qdlin,Tdlin,discharge_dQdV}` are gzip-4 + shuffle; `native/offset`, `row/cycle`,
  `row/cell_uid` and `vdlin` are **contiguous, uncompressed, unchunked**
  (`chunks is None`, `compression is None`, `shuffle False`).
* **The 1-D chunk is 256 KB on the five float32 natives but 512 KB on `t`**, which is
  float64 at the same `(65536,)` chunk shape. §1.4 gives the shape and leaves the
  asymmetry implicit.
* **Per-file lengths differ** and no reader may assume otherwise:

  | file | grid / row rows | `native/offset` | native 1-D length |
  |---|---|---|---|
  | `2017-05-12` | 38,811 | 38,812 | 40,951,666 |
  | `2017-06-30` | 24,920 | 24,921 | 32,094,849 |
  | `2018-04-12` | 51,007 | 51,008 | 38,822,223 |

  The three native lengths sum to **111,868,738**, matching `MANIFEST_v1.1.md` exactly.
* **`fillvalue` is `0.0` on the grids, not NaN.** Irrelevant to reads of written rows, but
  it means a fixture author who sizes a grid dataset larger than the rows written gets
  zeros, not NaN — the one mistake that would make the placeholder regression test pass
  for the wrong reason.

### 1.9 §3's read plan ignores the fact that makes the reader simple

§3 says reads are "per-cell slices" and that `native/offset` "is the only dataset read
whole" (408 KB). Both are unnecessarily pessimistic. Measured over all **140** struct
rows: within one file, a cell's `h5_row` values are **always a single contiguous ascending
block** (140/140 groups; `h5_row` ascends with `cycle` in every `(cell, file)` group).

Therefore:

* any contiguous cycle range of one cell is **one** `ds[lo:hi]` slice, on the grids and on
  `row/*` alike;
* the CSR offsets needed are **`offset[lo:hi+1]`**, never the whole dataset — so the 408 KB
  read is avoidable and the "only dataset read whole" claim should simply be dropped;
* a native field for that range is **one** `ds[offset[lo]:offset[hi]]` read, split
  afterwards in memory. That is what §2.4's measurements do.

`SPEC_v0.2.md` never states the contiguity. It is the single most load-bearing structural
fact about the files and it belongs in the spec.

### 1.10 Placeholders are a *subset* of series-invalid, not a second set

§1.6 and §7 decision 2 both read "series-invalid **and** placeholder", as if two
predicates had to be combined. Measured over all 114,738 rows:

* `is_placeholder == ~series_present` — **exactly**, row for row;
* every `is_placeholder=True` row has `is_series_valid=False`;
* all 46 are cycle 1 of a 2017-05-12 cell, and all 46 are `in_analysis_set=True`.

So `~is_series_valid` already covers the placeholders. One predicate is enough, and §2.2's
`drop_invalid_cells` is defined on that one predicate. This also means the nine components
are not independent: `series_present` fails on exactly the 46 placeholders and nothing
else.

### 1.11 The worst `Tdlin` is four times worse than §1.5 says

§1.5 reports `Tdlin_max = 523 °C` on `EL150800737364` cycle 368. True for that cycle. The
dataset's worst is **`Tdlin_max = 2,089.2 °C`** — `EL150800460653`, 2017-05-12, cycle 163.
That cycle fails **only** `series_grid_in_range`, so nothing at the summary level
(`is_clean_cycle`) catches it. For a team normalizing `Tdlin` as well as `Qdlin` this is
the number to quote.

### 1.12 §6's "cluster at labels 12–13 across 18 cells / 40 of the 46" is wrong

Measured on 2017-05-12, labels 12 and 13, `is_series_valid=False`: **17 cycles across 16
cells** of that batch's 46. Not 18 cells, and not 40 of 46.

### 1.13 §6's "6 positions with impossible `Qdlin`" conflates two failure modes

Six positions inside labels 1–25 fail `series_grid_in_range`. Only **four** of them carry
an out-of-band `Qdlin`:

| cell | cycle | `Qdlin` min … max (Ah) | `Tdlin_max` | failing components |
|---|---|---|---|---|
| `EL150800463871` | 13 | −9.73 … **+32.97** | 35.8 | grid |
| `EL150800464002` | 13 | −8.86 … **+31.03** | 34.5 | grid |
| `EL150800464865` | 12 | −2.16 … **+48.84** | 33.2 | grid |
| `EL150800464977` | 12 | −1.21 … **+45.34** | 30.7 | grid |
| `EL150800460514` | 12 | −0.18 … +0.99 | 35.0 | time_contiguous, duration, grid |
| `EL150800737364` | 13 | −0.62 … +1.05 | 37.5 | length_plausible, grid |

The last two have a physically plausible `Qdlin` and fail the grid check on another
channel. Stated correctly: **six positions fail `series_grid_in_range`; four of them carry
`Qdlin` up to +48.8 Ah on a 1.1 Ah cell.** The in-window band is **−9.73 … +48.84 Ah**,
and the in-window worst `Tdlin_max` is a harmless 40.7 °C — the ±1,400 Ah and 2,089 °C
extremes are all outside the first 25 cycles, which is worth saying plainly: an early-window
model is hurt by ~45 Ah, not by ~4,000 Ah.

### 1.14 §4's constants block is entirely stale

§4 prescribes `V11_ZENODO_DOI = None`, `V11_ZENODO_RECORD_ID = None`,
`V11_ZENODO_BASE = None`, `V11_DATA_TAG = None` with `TODO`s, and §3 reasons from "while
`V11_ZENODO_BASE is None`". Shipped 0.2.2 has them filled, and the record is published:

| constant | shipped value |
|---|---|
| `V11_ZENODO_DOI` | `10.5281/zenodo.23984188` (version DOI) |
| `V11_ZENODO_CONCEPT_DOI` | `10.5281/zenodo.23984187` |
| `V11_ZENODO_RECORD_ID` | `23984188` |
| `V11_ZENODO_BASE` | `https://zenodo.org/api/records/23984188/files` |
| `V11_ZENODO_VERSION_LABEL` | `1.1.0` |
| `V11_DATA_TAG` | `v1.1` |

Published 2026-11-05. The unpublished branch survives only as a tested fallback for a fork
that blanks the constants (`_v11_unpublished_message`), which is correct and should stay.
I re-read the record's file listing on 2026-11-09: **all 8 files present, every size
identical to `V11_SIZE_BYTES`, every MD5 identical to `V11_ZENODO_MD5`**, and each entry's
`links.content` is exactly the `{base}/{name}/content` shape `constants.v11_url_for`
builds. §4's "3 of the 8 hashes must be recorded at publication" is satisfied — the MD5s
of `SHA256SUMS.txt`, `EXTRACTION.md` and `LICENSE.txt` are in `MANIFEST_v1.1.md`.

### 1.15 §3's "per-batch lazy download … inherited from v0.1.1" understates what shipped

0.2.2 does not merely inherit the v1.0 machinery. `resolve_v11_dir(data_dir=None,
names=None)` **already takes the filename list**, `_populate_v11_cache(names)` fetches only
the missing ones, and `_download_v11_one` already carries the retry classification, the
truncated-transfer detection and the atomic `.part` rename. Its own docstring names the
v0.3.0 caller. So **v0.3.0 writes no download code at all** — it calls
`resolve_v11_dir(names=(index, cells, one_or_two_h5))`. §4's access section is a
description of existing behaviour, not a build item.

### 1.16 The test matrix in §5 is not achievable as written

§5 asks for "two h5py versions (the 3.16.0 that wrote the files, and the oldest
supported — floor `h5py>=3.0` … the floor is *tested*, not asserted)".

**Measured, not assumed:** on Python 3.13 the oldest h5py with a `cp313` wheel is
**3.12.1**. Every release from 3.0.0 to 3.11.0 has no `cp313` wheel and fails to build
from source in this environment (the numpy build backend fails first). So the floor that
can actually be *run* here is 3.12.1, not 3.0.

What I did test: a clean venv with **h5py 3.12.1 (HDF5 1.14.4)** opens all three real
files and reads correctly — `vdlin` float64 3.5→2.0, `row/cell_uid` as `|S16`
(`b'EL150800460514'`), `native/offset` int64 `[0, 2, 1089]` (the placeholder's 2 samples
visible in the offsets), `grid/Qdlin[0]` all-NaN, a `native/t` slice, and all three
dataset attributes. **Files written by HDF5 2.0.0 read correctly under HDF5 1.14.4.** §5's
conclusion ("the files use nothing newer than gzip + shuffle, so an old h5py suffices") is
supported by evidence for the first time, one version deep. §6 keeps the declared floor and
says plainly which part of it is tested.

Also: §5 says "pandas 2.x and 3.x". The matrix for this release is pinned to **2.2.3,
3.0.6 and 3.1.1**.

### 1.17 The fixture in §5 cannot hold a two-file cell

§5 specifies one `tiny_within_cycle.h5` and asks it to contain "a continuation cell split
across two files whose `batch_date` ≠ `source_batch_date`". One file cannot express that.
§7 replaces it with two HDF5 files plus one index CSV.

### 1.18 `open_batch(batch_date, …)` is named after the trap it documents

§3 gives `open_batch(batch_date, …)` and then spends a paragraph saying the argument is
really a `source_batch_date`. Rename the parameter to **`source_batch_date`** so a reader
who passes `cells.batch_date` gets a name mismatch at the call site instead of a wrong
file. (Shipped 0.2.2 already names the correction everywhere else;
`load_cell_features`'s `segments_resolved` is the per-cell record of it.)

### 1.19 "40.5 MB" is an `nbytes`, not a memory requirement

§1.8 and §3 quote 40.5 MB for the 25-cycle window. `X.nbytes` is 38.6 MiB (= 40.5 MB
decimal, consistent). But the number a Colab user needs is the **peak process RSS**, which
includes the index: **140 MiB**. §5 states RSS throughout.

### 1.20 Confirmed exactly as written

Re-measured, all identical to `SPEC_v0.2.md`:

* every dtype in §1.4's table, the `(65536,)` and `(64, 1000)` chunk shapes, gzip-4 +
  shuffle, `row/cell_uid` as `|S16` needing `.decode()`;
* **135** cells, **140** struct rows, per-file cell counts **46 / 48 / 46**, rows
  **38,811 / 24,920 / 51,007** = **114,738**; `(cell_uid, cycle)` unique;
* **113,559** `in_analysis_set` (= `len(analysis_set_cycles.csv)`), **1,179**
  `beyond_crossing` (all 2017-06-30), **46** placeholders;
* `is_series_valid=False` on **249** cycles across **97** cells;
  `series_grid_in_range=False` on **48** across **32**;
* `vdlin` byte-identical in all three files, monotone decreasing, and differing from
  `np.linspace(3.5, 2.0, 1000)` in **15 of 1000 points by ≤ 4.440892e-16**;
* **113 of 140** struct rows have `source_struct_index + 1 != source_channel`
  (§1.20 note: `SPEC_v0.2.md` cites the per-batch 37/46, 30/48, 46/46 from
  `exploration/REPORT.md`, which sums to 113 — consistent);
* every cell has **≥ 170** segment-1 cycles (minimum `EL150800460605` = 170, next 326), so
  a 25-cycle or 50-cycle window never crosses a file;
* the **five** two-file cells, their channels and their exact cycle spans (§3.1).

One confirmation worth promoting out of a footnote: **the index's first-appearance cell
order is byte-identical to `analysis_set_cells.csv`'s row order** (ascending batch, then
ascending channel; first five `EL150800460514, EL150800460486, EL150800460623,
EL150800464977, EL150800464865`). `SPEC_v0.2.md` §3 promises `load_conditioning` is
"aligned row-for-row with `load_early_window`'s `cell_uid`" without ever saying what the
order *is*. It is this one, it is free, and §2.3 makes it the contract.

---

## 2. The API

Four public functions, in `matr_clean/series.py`, re-exported from `__init__`. `_h5.py` is
the only module that imports `h5py`.

### 2.1 `load_series` — the gateway

```python
def load_series(
    cell,                                     # str, or sequence of str
    cycles=None,                              # None | int | sequence[int] | range | slice
    fields=("Qdlin", "Tdlin", "discharge_dQdV"),
    clean=False,                              # v1.0 is_clean_cycle -> mask
    require_series_valid=True,                # v1.1 is_series_valid -> mask
    beyond_crossing=False,                    # structural: the 1,179 rows
    drop_invalid_cells=False,
    data_dir=None,
    v11_dir=None,
) -> dict
```

**`cycles` is the point of the function.** It accepts:

| form | meaning |
|---|---|
| `None` | every cycle the index holds for that cell |
| `10` | the single label 10 |
| `range(1, 26)` / `[1, 2, 3]` / `np.arange(100, 151)` | those labels, in the order given |
| `slice(100, 200)` | labels 100…199, a convenience over `range` |

Labels are **cycle labels as stored** (`cycle` = struct index + 1), never row positions and
never positions in the returned array. A requested label with no row in the index is a
**masked position that keeps its label** — gaps are never closed, and the returned array
length always equals `len(cycles)`.

`fields` draws from `V11_NATIVE_FIELDS + V11_GRID_FIELDS` in any mix. An unknown name
raises `ValueError` naming the nine valid ones.

**Return value** (a plain `dict`; keys always present unless marked):

| key | shape / dtype | meaning |
|---|---|---|
| `cell_uid` | `(n_cells,)` `<U14` | row order = `analysis_set_cells.csv` order, restricted to the requested cells (§2.3) |
| `cycle` | `(n_cells, n_cycles)` int32 | **the label at each position**; `0` only where a row is padded under `cycles=None` |
| `valid` | `(n_cells, n_cycles)` bool | the mask to train on: `present & requested-predicates` |
| `present` | `(n_cells, n_cycles)` bool | `False` = the index has no such `(cell, cycle)` row at all — a real gap, distinct from a bad measurement |
| `is_placeholder` | `(n_cells, n_cycles)` bool | as stored |
| `is_series_valid` | `(n_cells, n_cycles)` bool | as stored |
| `is_clean_cycle` | `(n_cells, n_cycles)` bool | as stored (v1.0) |
| `beyond_crossing` | `(n_cells, n_cycles)` bool | as stored |
| `n_samples` | `(n_cells, n_cycles)` int32 | native length of each row; `0` where absent |
| `source_batch_date` | `(n_cells, n_cycles)` `<U10` | **which file each row came from** — the continuation record, per row |
| `segment` | `(n_cells, n_cycles)` int8 | 1 or 2; `0` where absent |
| *each grid field* | `(n_cells, n_cycles, 1000)` float32 | **as stored**; NaN on placeholder rows, the real ±Ah numbers on out-of-band rows |
| *each native field* | nested list, `out["V"][i][k]` → 1-D array or `None` | ragged by decision 1; `None` at an absent or padded position |
| `vdlin` | `(1000,)` float64 | present iff a grid field was requested |
| `fields` | tuple | as passed, resolved order |
| `field_kind` | `{name: "grid" \| "native"}` | so a caller never has to guess the return type |
| `batch_date` | `(n_cells,)` `<U10` | **as stored** — the *first* segment's, on every row. Kept so `load_cell_features` joins, and documented as not a file selector |
| `policy` | `(n_cells,)` `<U16` | `policy_canonical` as stored |
| `fold` | `(n_cells,)` int8 | as stored; `-1` = held-out test cell |
| `cell_flags` | `{name: (n_cells,) bool}` | `is_continuation`, `has_eol_label`, `thermocouple_fault`, `exclude_from_deltaq_features`, as stored |
| `filters` | dict | the request, and the per-reason counts of what was masked or dropped |

**No `X`.** Stacking native and grid fields into one tensor is not expressible (ragged vs
fixed), so `load_series` returns one entry per field and `load_early_window` is the
function that stacks (§2.2).

### 2.2 `load_early_window` — a thin wrapper, grid fields only

```python
def load_early_window(
    n_cycles=25,
    fields=("Qdlin", "Tdlin", "discharge_dQdV"),
    window="measured",                        # "measured" | "labels"
    cells=None,
    include_test=False,
    clean=False,
    require_series_valid=True,
    drop_invalid_cells=False,
    data_dir=None,
    v11_dir=None,
) -> dict
```

It resolves the per-cell label list for the chosen convention, calls `load_series` once per
source file, and stacks the grid fields into

* `X` — `(n_cells, n_cycles, n_fields, 1000)` float32,

then returns `X` plus **every key `load_series` returns**, unchanged. A native field in
`fields` raises `ValueError`: a ragged field cannot be stacked, and silently padding it
would be the zero-fill this release exists to prevent.

`window="measured"` (the default) takes each cell's first `n_cycles` rows with
`is_placeholder=False`; `window="labels"` takes labels `1…n_cycles`. They differ only for
the 46 cells of 2017-05-12, whose labels shift by one under `"measured"`. The reasoning and
the ΔQ(100−10) cost are `SPEC_v0.2.md` §6's and are unchanged; the `cycle` matrix is always
returned, so which labels you got is never ambiguous.

**This function is built only if it is cheap.** On the design above it is ~60 lines over
`load_series` with no new file access, which qualifies. If the label-resolution for
`"measured"` turns out to need anything beyond `groupby.head`, it ships in a later release
and the loop in §2.5 is the documented substitute. Either way `load_series` lands first
(§8).

### 2.3 The alignment contract

`cell_uid` is always ordered as `analysis_set_cells.csv`'s rows — ascending `batch_date`,
then ascending `channel` — restricted to the cells requested and, when `include_test=False`,
to `fold != -1`. This is measurably the same order the index's cells first appear in
(§1.20), and it is the order `load_conditioning` already returns, so

```python
cond = mc.load_conditioning()                      # X (n, 4), cell_uid (n,)
win  = mc.load_early_window(n_cycles=25)           # X (n, 25, 3, 1000), cell_uid (n,)
assert (cond["cell_uid"] == win["cell_uid"]).all() # holds by construction
```

needs no join. `cell_uid` is returned decoded (`str`), never as the stored `|S16` bytes.

### 2.4 `load_vdlin` and `open_batch`

```python
def load_vdlin(data_dir=None, v11_dir=None) -> np.ndarray
```
`(1000,)` float64, **as stored** — never reconstructed from `np.linspace`, which differs in
15 points (§1.20). Read from whichever batch file is already local; identical in all three.

```python
def open_batch(source_batch_date, data_dir=None, v11_dir=None) -> "h5py.File"
```
The escape hatch: returns an `h5py.File` opened `mode="r"`, for anything the typed API does
not cover. The caller closes it (it is a context manager). The parameter is named
`source_batch_date`, not `batch_date`, for the reason in §1.18; passing a `batch_date` from
`load_cell_features` is the documented way to open the wrong file for the five continuation
cells.

### 2.5 Rolling evaluation needs no new function

A rolling-window loop needs four things, and `load_series` returns all four: the **labels**
it actually got (`cycle`), the **mask** (`valid`, plus the four raw flag matrices if the
caller wants its own predicate), the **gaps** (`present`, which separates "no such cycle"
from "a bad cycle"), and **arbitrary ranges** (`cycles=`). So:

```python
import matr_clean as mc

cycles_tbl = mc.load_cycle_features(clean=False, require_series_valid=False)  # plan from this
for start in range(1, 401, 25):
    w = mc.load_series("EL150800737364", cycles=range(start, start + 25))
    # w["Qdlin"]: (1, 25, 1000);  w["valid"]: (1, 25);  w["cycle"]: (1, 25)
    if not w["valid"].all():
        ...                      # the caller decides: skip the window, or mask the step
```

Confirmed: **no new function is needed for rolling evaluation**, and none is proposed. The
plan-the-ranges step reads the 77-column index once through the shipped
`load_cycle_features`; the per-range calls touch only the HDF5.

### 2.6 Defaults, stated once and bindingly

1. **Invalid and placeholder cycles are returned, masked.** Never interpolated, never
   zero-filled, never silently dropped. A placeholder grid row comes back all-NaN because
   that is what the file holds; an out-of-band row comes back as +48.8 Ah because that is
   what the file holds.
2. **Gaps are never closed.** `len(result) == len(cycles)` always; a missing label is a
   masked position that keeps its label and gets `present=False`.
3. **Cycle labels are always returned.** `cycle` is not optional and not suppressible.
4. **The mask predicate, by default, is `require_series_valid=True`** → `valid` is
   `present & is_series_valid`. Because placeholders nest inside series-invalid (§1.10),
   that one predicate masks all 46 of them. `clean=True` additionally requires v1.0
   `is_clean_cycle`; `require_series_valid=False, clean=False` masks nothing but absence.
5. **`beyond_crossing` is structural, not quality.** `False` (the default) means those
   1,179 rows are not in the requested set at all — same meaning as in
   `load_cycle_features`. It does not mask; it selects.
6. **No `nan_to_num`, no `fillna`, no clipping, no winsorising, no interpolation anywhere
   in `series.py` or `_h5.py`.** Enforced by a source-level test (§7).

### 2.7 `drop_invalid_cells` — measured, default off

```python
drop_invalid_cells=False      # True removes any cell with an invalid row in the range
```

`True` drops a whole cell from `cell_uid` (and every array's axis 0) if **any** row in the
requested range has `is_series_valid=False`. Because placeholders nest (§1.10), that single
predicate covers them. The dropped uids and the count land in `filters`, so a caller always
knows what left.

**Measured on the real index** — cells removed / kept, by window length and convention:

| N | convention | all 135 | non-test (fold ≠ −1), 108 | `in_paper_124`, 124 |
|---|---|---|---|---|
| 10 | `measured` | **2 removed → 133** | 2 → 106 | 1 → 123 |
| 10 | `labels` | 47 → 88 | 38 → 70 | 41 → 83 |
| **25** | **`measured`** | **18 removed → 117** | **14 → 94** | **16 → 108** |
| 25 | `labels` | 48 → 87 | 39 → 69 | 42 → 82 |
| 50 | `measured` | **18 removed → 117** | 14 → 94 | 16 → 108 |
| 50 | `labels` | 48 → 87 | 39 → 69 | 42 → 82 |

Three things to read off it:

* Under `"labels"` the floor is the 46 placeholders: a third of the cells are removed at
  **any** N, because label 1 of every 2017-05-12 cell is structurally empty. That is the
  cost of the label convention, and it is why `"measured"` is the default.
* Under `"measured"`, **N=25 and N=50 remove the same 18 cells.** The damage is concentrated
  in labels 12–13 (§1.12), so widening the window from 25 to 50 costs nothing extra.
  Narrowing to 10 costs only 2.
* `drop_invalid_cells=True` is a 13% cell loss at N=25 for a 0.5% cycle loss (48 of 3,375
  positions). Masking is almost always the better trade, which is why the default is off.
  The 18 are listed in the docstring; 17 lose one or two cycles each, and one —
  `EL150800453240`, inside the U15 splice run — has **all 25** of its first measured cycles
  invalid and contributes nothing usable to a 25-cycle model either way.

Position-level figures for the same windows, for the masking path:

| N | convention | positions | masked | cells with ≥1 masked | NaN positions (field-wise) |
|---|---|---|---|---|---|
| 10 | `measured` | 1,350 | 11 | 2 | 0 |
| 10 | `labels` | 1,350 | 56 | 47 | 46 × 3 fields |
| 25 | `measured` | 3,375 | 48 | 18 | 0 |
| 25 | `labels` | 3,375 | **93** | **48** | 46 × 3 = **138** |
| 50 | `measured` | 6,750 | 73 | 18 | 0 |
| 50 | `labels` | 6,750 | 118 | 48 | 138 |

The 93/48 under `"labels"` reproduces `SPEC_v0.2.md` §6 exactly. **Under `"measured"` there
is no NaN in `X` at all**, in any of the three window lengths — the placeholder rows are
never selected. That is the cleanest single argument for the default: there is nothing for
`nan_to_num` to do, so nothing it can quietly do wrong.

---

## 3. Dispatch, and the five two-file cells

### 3.1 Reconfirmed, from the index

| cell | channel | segment 1 — file, labels | segment 2 — file, labels |
|---|---|---|---|
| `EL150800460486` | 2 | `2017-05-12`, 1–1178 (n=1178) | `2017-06-30`, 1179–2159 (n=981) |
| `EL150800460514` | 1 | `2017-05-12`, 1–1189 (n=1189) | `2017-06-30`, 1190–1851 (n=662) |
| `EL150800460623` | 3 | `2017-05-12`, 1–1176 (n=1176) | `2017-06-30`, 1177–2236 (n=1060) |
| `EL150800464865` | 6 | `2017-05-12`, 1–1226 (n=1226) | `2017-06-30`, 1227–1708 (n=482) |
| `EL150800464977` | 5 | `2017-05-12`, 1–1225 (n=1225) | `2017-06-30`, 1226–1433 (n=208) |

Five cells, both segments on the **same channel**, no third segment anywhere
(`source_batch_date.nunique() > 1` for exactly these five). Per-file cell counts
46 + 48 + 46 = 140 struct rows over 135 distinct cells.

### 3.2 The dispatch rule

**Every file selection is made from the index's `source_batch_date`, per row, never from
`batch_date`.** `batch_date` in both v1.0 CSVs and in `within_cycle_cells.csv` is the
*first* segment's, on every row; a segment-2 row of a continuation cell says `2017-05-12`
while its bytes sit in `within_cycle_2017-06-30.h5`.

Concretely, `_h5.py` resolves a request in four steps:

1. Join the requested `(cell_uid, cycle)` pairs against the index → per row,
   `(source_batch_date, h5_row)`.
2. Group by `source_batch_date`. That set, and nothing wider, is the set of files to
   resolve, so `resolve_v11_dir(names=…)` is asked for one or two `.h5` files, never three.
3. Per file, per cell: the rows are one contiguous ascending block (§1.9), so take
   `lo = h5_row.min()`, `hi = h5_row.max() + 1` and slice once.
4. Open each file once, read every requested field for every requested cell of that file,
   close it before the next.

`source_batch_date` is also returned per row (§2.1), so a caller can always see which file
a value came from. A cell's full series is therefore **one or two** file opens, and a
25-cycle window is always **one** (every cell has ≥170 segment-1 cycles, §1.20).

### 3.3 Addressing

`cell_uid` is the only cell key. Channel and struct index are returned as provenance
(`load_cell_features().segments_resolved`) and never used to locate data, because 113 of
140 struct rows have `source_struct_index + 1 != source_channel` (§1.20). `h5_row` from the
index is the only row address; no code path computes a row from a channel, a struct index
or a position in any array.

---

## 4. Data access: Kaggle, Colab, local

Both routes are **already implemented and tested in 0.2.2** (§1.15). v0.3.0 only passes
HDF5 filenames where 0.2.2 passes CSV ones.

### 4.1 Route (a) — a folder the user supplies, hash-verified

Lookup order, unchanged: `v11_dir=` → `data_dir=` → `set_data_dir()` →
`$MATR_CLEAN_DATA_DIR` → a clone's `exploration/extract_out/` (then `exploration/`) → the
cache. A directory named explicitly **raises rather than falling back**, so a typo is
visible. The folder is only ever read; nothing is written to it, which is what makes
`/kaggle/input` and a mounted Drive usable directly.

Verification is per file, SHA-256 against `constants.V11_SHA256`, once per process
(`_V11_VERIFIED`). Only the files a call needs are verified: a user with one batch on disk
is never told the other two are missing. Measured hashing cost on this machine, warm cache:
**1,315 MiB/s** — 0.42 s for the 581.6 MB batch, 1.59 s for all 2.20 GB, 0.06 s for the
72.8 MB index. Hashing is not the bottleneck on local disk; over a FUSE-mounted Drive the
cost is read bandwidth, which I did not measure and should not guess.

A Kaggle dataset needs: `within_cycle_index.csv`, `within_cycle_cells.csv`, the batch
`.h5` file(s) in use, and — because `load_cycle_features` joins the v1.0 tables —
`analysis_set_cycles.csv`, `analysis_set_cells.csv`, `cell_inventory.csv`. All three CSVs
and the 2.2 GB fit the dataset size limit comfortably.

### 4.2 Route (b) — lazy per-batch download from the published record

`resolve_v11_dir(names=…)` falls through to `_populate_v11_cache(names)`, which fetches
**only the named missing files** into `~/.cache/matr_clean` (`$MATR_CLEAN_CACHE_DIR`
overrides). URLs come from `constants.v11_url_for` → `{base}/{name}/content`, the files
API's own `links.content`, pinned to the **version** record `23984188` — not the concept
DOI, which resolves to "latest" and would let the bytes change under a pinned caller. I
confirmed on 2026-11-09 that all 8 entries, their sizes and their MD5s match the constants
and that the `/content` shape is right (§1.14).

Inherited behaviour, all of it already tested:

* bytes go to a `.part` temp file in the destination directory and are `replace()`d over
  the target only after the response is fully read, so an interrupted attempt leaves
  nothing that looks finished;
* **truncated transfers are caught before the hash check.** `HTTPResponse.read(amt)`
  returns `b""` rather than raising when a connection drops mid-body, so a cut at 97% of a
  797.7 MB file looks like a file that ended. `_fetch_once` counts bytes written and
  compares against `Content-Length` (or `V11_SIZE_BYTES`), raising `IncompleteRead` — which
  is retryable — instead of letting it surface as `IntegrityError`, which is final and
  would tell the user their data is corrupt when a retry would have fixed it. **This matters
  far more at 0.6–0.8 GB than it did at 72.8 MB**, and it is the single best reason the
  download route needs no new code;
* retries only what a second attempt can fix, with backoff; a **wrong hash is final** — the
  file is deleted, the error raised, and the remaining files are not fetched.

**What a call downloads, worst case:** the index (72.8 MB) plus the cells table (14 KB)
plus one or two batch files.

| batch file | bytes |
|---|---|
| `within_cycle_2017-05-12.h5` | 797,659,714 |
| `within_cycle_2017-06-30.h5` | 581,592,476 |
| `within_cycle_2018-04-12.h5` | 823,392,641 |
| all three | **2,202,644,831** |

A 25-cycle window over **all 135 cells touches all three files**, so the default call is the
2.20 GB case. A window restricted to one batch's cells is 0.58–0.82 GB. One of the five
continuation cells' *full* series needs two files (1.38 GB); its first 25 cycles need one.

### 4.3 Kaggle with internet off

* **Route (b) is unavailable, by construction.** Every network call goes through
  `urllib.request.urlopen` in `_locate._fetch_once`; with no egress it raises, is classified
  as retryable, exhausts `MAX_ATTEMPTS` and surfaces as `DownloadError` carrying the offline
  message that names both the `v11_dir=`/`$MATR_CLEAN_DATA_DIR` routes. The failure is
  explicit and already tested — the suite's `urlopen` guard exercises exactly this path.
* **Route (a) is the only route**, and it works fully: attach the files as a Kaggle dataset,
  pass `v11_dir="/kaggle/input/<slug>"`. Read-only is fine.
* So the Kaggle instruction is one line: *attach the dataset, pass `v11_dir=`, never rely on
  the download.* Worth stating in `USAGE.md` because the default-on-internet Kaggle notebook
  and the competition-style internet-off notebook behave differently for the same code.

### 4.4 Colab, and the cost of a runtime reset

A Colab runtime is discarded on reset, and so is `~/.cache/matr_clean`. The recurring cost
of route (b) is therefore the full download, every runtime:

| what the session needs | re-downloaded per reset |
|---|---|
| index + cells only (0.2.2 functionality) | **72.9 MB** |
| + one batch | 0.65–0.90 GB |
| + all three batches (the default 135-cell window) | **2.28 GB** |

`USAGE.md` already recommends a **Drive copy as the documented default** for exactly this
reason, and that recommendation stands: Drive is paid once, the loader reads the folder in
place and never writes to it, and verification is per file. The per-batch download stays the
alternative for a session that genuinely touches one batch.

Two things to add to `USAGE.md` §"The large files, Colab and Drive" that it cannot say
today: that the *default* `load_early_window` call spans all three files (so the per-batch
saving applies only to a batch-restricted request), and that hashing is read-bandwidth
bound over Drive, not CPU bound (1,315 MiB/s locally).

---

## 5. Memory

### 5.1 Measured, in isolated processes

Peak **RSS** (`ru_maxrss`), one process per row so no earlier phase inflates the figure.
Python 3.13.5, h5py 3.16.0, files on local disk.

| operation | payload | peak RSS | wall |
|---|---|---|---|
| index, 8 columns (`cell_uid, cycle, segment, source_batch_date, h5_row, n_samples, is_placeholder, is_series_valid`) | 17 MiB resident | **96 MiB** | 0.1 s |
| index, all 77 columns | 69 MiB resident | **306 MiB** | 0.1 s |
| **25 cycles × 3 grid fields × 135 cells, `window="measured"`** | `X` 38.6 MiB | **140 MiB** | 0.5 s |
| same, `window="labels"` | `X` 38.6 MiB | **141 MiB** | 0.5 s |
| **largest cell, full series, 6 native + 3 grid** (`EL150800460623`, 2,236 cycles, 2,370,992 samples, two files) | 88.9 MiB | **184 MiB** | 0.4 s |
| same cell, 6 native fields only | 63.3 MiB | **160 MiB** | 0.3 s |
| everything, all fields all cells (**no code path builds this**) | 4.51 GB | — | — |

### 5.2 The rules that produce those numbers

* **The lean index is what `series.py` reads.** 8 columns at 96 MiB peak against 77 columns
  at 306 MiB is a 210 MiB difference on a Colab instance, for free. `series.py` reads the
  lean set via `pandas.read_csv(usecols=…)` and caches it in `features._V11_CACHE` under its
  own key; a caller who also wants the 69 columns of diagnostics calls
  `load_cycle_features`, which caches the wide frame separately. Neither forces the other.
* **Lazy per batch.** Files are opened one at a time and closed before the next, so at most
  one `h5py.File` is live. The 25-cycle default opens three files in sequence, never
  together.
* **Lazy per cell, per field.** The read unit is one contiguous slice of one dataset for one
  cell (§1.9). No dataset is ever read whole — including `native/offset`, which §1.9
  corrects `SPEC_v0.2.md` on.
* **One native staging buffer at a time.** A cell's native field is read as one
  `ds[offset[lo]:offset[hi]]` block and split into per-cycle views, then the block is
  released before the next field. That is why the full-series figure is 184 MiB and not the
  3× that six simultaneous buffers would cost.
* **Nothing array-shaped is cached across calls.** `features._V11_CACHE` holds DataFrames
  only; `X`, the ragged lists and the masks are returned and forgotten.
* **No code path materialises the 4.51 GB.** `cycles=None` is per cell, and `cell` accepting
  a sequence does not change the per-cell read unit — but a caller who passes all 135 uids
  *with* `cycles=None` *and* all nine fields asks for the 4.51 GB explicitly. `load_series`
  estimates the payload from `n_samples` before reading and raises `MemoryError` with the
  figure and the suggestion to loop, above a `max_bytes=` ceiling (default 2 GiB,
  settable, `None` to disable). This is the one new guard v0.3.0 needs that 0.2.2 has no
  equivalent of.

### 5.3 Headroom

The stated use case is ~80 cells on Colab (13 GB RAM), Kaggle (~30 GB) and local machines.
The 25-cycle default at **140 MiB** leaves the whole budget for the model; even the
pessimistic single-cell full-series read at **184 MiB** does. The binding constraint for
this release is **disk and download bandwidth (2.20 GB), not RAM.**

---

## 6. The optional dependency

`pyproject.toml` already declares it, from 0.2.2:

```toml
[project.optional-dependencies]
series = ["h5py>=3.0"]
```

`h5py` is imported **inside `_h5.py`'s functions**, never at module scope, so
`import matr_clean` and every 0.2.x function keep working without the extra. Absent, the
four new functions raise

```
ImportError: matr_clean.load_series needs h5py, which is not installed.
             Install the 'series' extra:  pip install 'matr-clean[series]'
             (h5py>=3.0; tested on 3.12.1 and 3.16.0)
```

— one message, naming the function, the package, the extra and the tested versions.

**The floor is tested, not assumed — one version deep.** §1.16 has the measurement: on
Python 3.13, h5py 3.0.0–3.11.0 have no `cp313` wheel and will not build here, so **3.12.1
is the oldest version that can be run in this environment**, and it reads all three real
files correctly under HDF5 1.14.4 against files written by HDF5 2.0.0. The declared
`>=3.0` therefore rests on two things: a tested 3.12.1, and the fact that the files use
nothing beyond gzip + shuffle on plain contiguous and chunked datasets, all of which h5py 3.0
had. **Recommendation: keep `h5py>=3.0` and say in `pyproject.toml` and `USAGE.md` that
3.12.1 is the oldest *tested* version**, rather than raise the declared floor to 3.12.1 —
raising it would needlessly exclude a working Python 3.9/3.10 environment, which is exactly
the environment the 3.9 floor exists for. If a 3.9 or 3.10 interpreter becomes available,
the honest test is h5py 3.1.0 there (the oldest with a `cp39` wheel); until then the gap is
recorded in §9, not papered over.

**The Python 3.9 floor stays statically checked**, as `tests/test_python39_floor.py` already
does — `ast.parse(..., feature_version=(3, 9))` over every module plus the grep for
constructs that parse everywhere and fail at import. `series.py` and `_h5.py` are picked up
automatically by its `PACKAGE.glob("*.py")`, and its `test_there_are_modules_to_check`
floor of 6 modules should rise to 8. Only Python 3.13 exists on this machine, so a real
3.9 run remains unavailable (§9).

---

## 7. Tests

### 7.1 The fixture

`tests/fixtures/make_fixture.py` — committed, deterministic, `track_times=False`, a few KB —
writes **two** HDF5 files plus one index CSV (§1.17):

```
tests/fixtures/tiny_A.h5        mirrors within_cycle_2017-05-12.h5
tests/fixtures/tiny_B.h5        mirrors within_cycle_2017-06-30.h5
tests/fixtures/tiny_index.csv   the same 77 columns, a handful of rows
tests/fixtures/tiny_cells.csv   the 9 columns of within_cycle_cells.csv
```

Each `.h5` mirrors the real layout **exactly**: no root attributes; `/vdlin` float64
`(1000,)` contiguous with its `units` and `note`; `/native/offset` int64 `(n+1,)`
contiguous; `/native/{I,V,T,Qc,Qd}` float32 and `/native/t` float64, 1-D, chunked
`(65536,)`, gzip-4 + shuffle, with `units`; `/grid/{Qdlin,Tdlin,discharge_dQdV}` float32
`(n, 1000)`, chunked `(64, 1000)`, gzip-4 + shuffle, with `grid`, `units` and the same
`note`; `/row/cycle` int32 and `/row/cell_uid` `|S16`, both contiguous. Grid datasets are
sized to exactly the rows written, because the real `fillvalue` is `0.0` and an oversized
dataset would make the placeholder test pass for the wrong reason (§1.8).

By construction the fixture contains:

* a **placeholder** cycle — 2 native samples of literal `0.0`, an all-NaN grid row,
  `is_placeholder=True`, `series_present=False`, `is_series_valid=False`;
* an **out-of-band `Qdlin`** cycle, around +45 Ah, with `series_grid_in_range=False` and
  **no NaN** — so the two failure modes are provably independent;
* a **continuation cell** with rows in both files, `batch_date` = file A's on every row and
  `source_batch_date` differing per segment;
* a cell whose `source_struct_index + 1 != source_channel`;
* a **gap**: a cell missing an interior cycle label, so `present=False` is reachable;
* a cell whose rows are a contiguous `h5_row` block starting at a nonzero offset.

Committed, so the whole suite runs with no data present.

### 7.2 Regression tests, each with the number it defends

| # | test | asserts |
|---|---|---|
| a | **placeholders masked, not zero-filled** | the placeholder position returns `valid=False`, `is_placeholder=True`, and `X` there is **all-NaN, never `0.0`**; its native row holds literal `0.0`, so the flag is the only signal; `is_placeholder` survives every combination of `clean`/`require_series_valid`/`drop_invalid_cells`. On real data: **46** rows, all cycle 1 of 2017-05-12, all `in_analysis_set` |
| a′ | the `nan_to_num` trap | `np.nan_to_num(X)` changes **exactly** the placeholder grid positions and **no** out-of-band value — the fixture proves the two are independent |
| b | **impossible `Qdlin` masked** | `series_grid_in_range=False` on **48** cycles / **32** cells, **34** of them `is_clean_cycle=True` in v1.0; `is_series_valid=False` on **249** cycles / **97** cells; those positions are present in `X` with their real values (so the mask, not a repair, is what protects a normalization); extremes **+1,430.7 Ah** (`EL150800460511`, 2017-06-30, cycle 247) and **−4,030.3 Ah** (`EL150800737364`, 2018-04-12, cycle 368); worst `Tdlin_max` **2,089.2 °C** (`EL150800460653`, cycle 163) — §1.11 |
| b′ | the in-window figures | under `window="labels"`, N=25: **93** masked positions across **48** cells, **138** NaN field-positions (46 × 3); under `window="measured"`, N=25: **48** masked across **18** cells and **zero** NaN; `drop_invalid_cells=True` removes **18 / 48** cells respectively (§2.7, all nine rows of both tables) |
| c | **five two-file cells, dispatch on `source_batch_date`** | all five resolve; each segment's rows come from the file its `source_batch_date` names; the exact spans of §3.1; and a **deliberately `batch_date`-dispatched lookup is asserted to fail or to return different bytes**, so the trap cannot regress silently. On the fixture, both directions are checkable without data |
| d | **addressing is never positional** | for the fixture cell with `source_struct_index + 1 != source_channel`, every accessor returns the `h5_row`-addressed row, and a position-addressed lookup is asserted to differ. Mirrors `exploration/test_cell_addressing.py`. On real data: **113 of 140** struct rows are off-position |
| e | **no NaN-to-zero anywhere in the code path** | *source-level*: `series.py` and `_h5.py` contain no `nan_to_num`, `fillna`, `np.clip`, `interp`, `ffill`, `bfill` or `dropna` — asserted by AST walk, not grep, so a renamed import cannot hide. *Behavioural*: for a request containing a placeholder, `np.isnan(X).sum()` equals the known placeholder count exactly, and `(X == 0.0).sum()` on those rows is **0** |
| f | gaps are never closed | a request for a range spanning the fixture's missing label returns `len(cycles)` positions, with `present=False` and the **label preserved** at the gap; no position is shifted |
| g | labels always returned | `cycle` is present in every return of all four functions, under every argument combination; `cycle` is never all-zero for a request that matched rows |
| h | masks vs drops | `X.shape` is identical under every `clean`/`require_series_valid` setting; only `valid` changes. `drop_invalid_cells=True` is the **only** argument that changes axis 0, and it reports the dropped uids in `filters` |
| i | alignment contract | `load_conditioning()["cell_uid"]` equals `load_early_window()["cell_uid"]` element-wise; both equal `analysis_set_cells.csv`'s order filtered to `fold != -1`; **135** cells unfiltered, **108** with `include_test=False`, **124** `in_paper_124` |
| j | `vdlin` as stored | `load_vdlin()` is float64 `(1000,)`, monotone decreasing, 3.5 → 2.0, byte-identical across all three files, and differs from `np.linspace(3.5, 2.0, 1000)` in **15 of 1000 points by ≤ 4.440892e-16**; `series.py` contains no `linspace` |
| k | dtypes and shapes as stored | `t` float64, the other five natives float32, the three grids float32, `vdlin` float64, `row/cycle` int32, `cell_uid` decoded from `\|S16`; grid returns are `(n_cells, n_cycles, 1000)` and native returns are ragged lists, never padded |
| l | contiguity invariant | on real data, every `(cell_uid, source_batch_date)` group's `h5_row` is one ascending contiguous block — **140/140** (§1.9). This is what licenses the single-slice reader, so it is asserted, not assumed |
| m | per-file row counts | **38,811 / 24,920 / 51,007** grid rows; `native/offset` **38,812 / 24,921 / 51,008**; native 1-D **40,951,666 / 32,094,849 / 38,822,223**, summing to **111,868,738** |
| n | `h5py` absent | with `h5py` unimportable (`sys.modules` patched), `import matr_clean` succeeds, every 0.2.x function works, and each of the four new functions raises `ImportError` naming the `series` extra |
| o | lazy open | a counting wrapper around `h5py.File` proves a 25-cycle single-batch request opens **one** file, a full continuation-cell series opens **two**, and no request opens a file it does not read from |
| p | `max_bytes` guard | an all-cells × all-cycles × all-fields request raises `MemoryError` with the estimated payload in the message, before any dataset read; `max_bytes=None` disables it |
| q | no writes | the integration run leaves every file's size and mtime unchanged, and every `h5py.File` is opened `mode="r"` (asserted by wrapping the opener) |
| r | 3.9 floor | `tests/test_python39_floor.py` picks up `series.py` and `_h5.py`; its module-count floor rises from 6 to 8 |

### 7.3 Integration, and staying offline

* **Integration tests skip unless `MATR_CLEAN_TEST_DATA` is set**, exactly as 0.2.2's do,
  and are pointed read-only at `exploration/extract_out/` or the Zenodo cache. Every real
  number in §7.2 is an integration assertion; its fixture counterpart is what CI runs.
* **The suite stays offline by construction.** `tests/conftest.py` already replaces
  `urlopen` with one that raises, unsets `MATR_CLEAN_DATA_DIR`, points the cache at
  `tmp_path` and stubs `_locate._sleep`, all autouse. v0.3.0 adds no network test outside
  the existing `network` marker (which needs `MATR_CLEAN_TEST_NETWORK=1`). Nothing in
  §7.2 touches the network.
* **Matrix.** pandas **2.2.3**, **3.0.6**, **3.1.1** × h5py **3.12.1** and **3.16.0**
  (§6 for why not 3.0). Python 3.9 statically, 3.13 actually.

---

## 8. Release plan

### 8.1 Version

**`loader-v0.3.0`**, as reserved. It is a minor bump: four new public functions, one new
optional dependency already declared in 0.2.2, and **no change to any shipped signature or
return value**. Nothing in §2 alters `load_cycles`, `load_cycle_features`,
`load_cell_features`, `load_conditioning`, `cv_splits` or `describe`'s existing output.

### 8.2 Build order — most-needed first

| step | contents | why here |
|---|---|---|
| **1** | `_h5.py`: the index→`(file, h5_row)` resolver, the per-file/per-cell slice reader, the lazy `h5py` import and its `ImportError`. No public surface. | Everything else is a call into it. Testable against the fixture alone. |
| **2** | **`load_series`** + **`open_batch`** + `load_vdlin` | `load_series` is the gateway (§2.1) and `open_batch` is the escape hatch that makes anything it does not cover possible *today*. Shipping these two first means the team is never blocked on a loader feature. `load_vdlin` is ten lines and the x-axis for every plot. |
| **3** | tests a–r against the fixture; integration behind `MATR_CLEAN_TEST_DATA` | The regression numbers are the deliverable, not a follow-up. |
| **4** | **`load_early_window`** | A wrapper over step 2 (§2.2). Built here if it stays thin; otherwise deferred with the §2.5 loop documented as the substitute. |
| **5** | `USAGE.md`, `README.md`, `describe()`, docstrings | §8.3. Done last so they describe what exists. |

Steps 1–3 are the release's substance. If time runs out, **1–3 is a shippable 0.3.0** and
`load_early_window` becomes 0.3.1 — which is precisely why the design priority puts
`load_series` first.

### 8.3 Docs that currently promise v0.3.0 behaviour and would need updating

Found by grep over the tree at `2d2fae7`. All of these are promises, not bugs; they need to
change from future to present tense, and five of them state something §1 corrects.

| file | lines | what it promises | action |
|---|---|---|---|
| `USAGE.md` | 592–603 | "### The early-cycle window, in v0.3.0"; `load_early_window(n_cycles=25)` "will default to `window="measured"`" | present tense; **and fix the in-window findings** — §1.12's 18-cells/40-of-46 and §1.13's "6 positions with impossible `Qdlin`" are both repeated here |
| `USAGE.md` | 607–634 | "## The large files, Colab and Drive (v0.3.0)"; "what is still to come is the code that *reads* the HDF5" | present tense; add §4.3 (Kaggle internet-off), §4.4 (the default call spans all three files), §4.1 (hashing is read-bandwidth bound) |
| `USAGE.md` | 683, 712–719, 728 | the field table marking nine series + `Vdlin` as "v0.3.0" | retag as shipped |
| `USAGE.md` | 325, 542 | "in v0.3.0"; "the array-returning functions follow the same principle differently" | present tense; restate §2.6 |
| `README.md` | — | the v0.2.2 feature list | add the four functions and the `series` extra |
| `matr_clean/__init__.py` | 33 | "arrive in v0.3.0 behind an optional `series` extra" | present tense; add to `__all__` |
| `matr_clean/features.py` | 18, 330 | "those arrive with v0.3.0" | point at `load_series` |
| `matr_clean/features.py` | 535 | `load_conditioning`'s "v0.3.0's `load_early_window` **will** reproduce exactly" | becomes the tested contract of §2.3 — test **i** |
| `matr_clean/loaders.py` | 363 | "live in the HDF5 files … and arrive in v0.3.0" | point at `load_series` |
| `matr_clean/loaders.py` | 716–725, 739, 742 | `describe()`'s field table tagging all ten entries "v0.3.0", and the two "arrive in v0.3.0" lines | retag to "0.3.0" as shipped; `describe()` is the thing a user runs first, so a stale tag here is the most misleading of the lot |
| `matr_clean/_locate.py` | 816 | `resolve_v11_dir`'s "v0.3.0 passes the HDF5 filenames it needs instead" | becomes a statement of fact |
| `pyproject.toml` | `series` extra comment | "v0.3.0 reads the three HDF5 files"; "v0.2.0 itself never imports h5py … installing without this extra is the normal case today" | present tense; add "oldest tested 3.12.1" (§6) |
| `CITATION.cff` | version | `0.2.2` → `0.3.0` |
| `SPEC_v0.2.md` | §3, §5, §6, §7 | superseded for everything HDF5 | **not edited.** A one-line header pointing at this file is the only change worth making, and even that is the maintainer's call |

No document promises a derived or early-window *file*, and none is designed, sized or
proposed here.

---

## 9. What I could not confirm

* **The h5py floor below 3.12.1.** Measured, not guessed: no `cp313` wheel exists for h5py
  3.0.0–3.11.0 and they do not build from source in this environment. `>=3.0` stays a
  reasoned claim about the HDF5 features the files use; 3.12.1 is the oldest *run* version
  (§1.16, §6). A 3.9 or 3.10 interpreter would make h5py 3.1.0 testable; neither exists
  here.
* **Python 3.9 at runtime.** Only `/usr/bin/python3.13` is installed. The floor stays
  statically checked, as it already is.
* **Colab and Kaggle, actually.** Neither was run. The §4.4 download figures are the
  published file sizes, and the §4.3 internet-off behaviour is read off `_locate.py`'s
  tested code paths — not observed in a Kaggle session. The Drive read-bandwidth cost of
  hash verification is **not measured** and is deliberately left unquantified.
* **Download throughput from Zenodo.** I read the file *listing* only. No file was
  downloaded, so there is no measured time for 0.58–0.82 GB, and the retry/truncation
  handling was not exercised against the real record (it is covered by
  `tests/test_v11_download.py` against stubs).
* **Whether `is_clean_cycle` stays as it is.** `MANIFEST_v1.1.md` open decision 1 is still
  open. If the 171 corrections are applied instead, `analysis_set_cycles.csv` changes, its
  SHA-256 changes, and `constants.SHA256` plus every shipped 0.1.x/0.2.x pin breaks. That is
  a release-ordering dependency on 0.3.0, not just a data question, and it is unchanged from
  `SPEC_v0.2.md` §9.
* **The `v1.1` merge.** `within-cycle-extraction` is still not a descendant of `main`
  (it branched at `09f1964`), so a merge, not a fast-forward, is needed and `_locate.py`
  is the file that conflicts. Not re-verified in this pass; I did not switch that clone.
* **Whether 0.3.0 should also expose a ΔQ(100−10) helper.** `SPEC_v0.2.md` §8 Q4 defers it.
  With `load_series(cell, cycles=[10, 100])` it is three lines of caller code, so I propose
  keeping it deferred — but that is a judgement, not a measurement.

---

## 10. Questions for the colleague

Only two, both of which change the defaults above and neither of which I can answer from the
data:

1. **Which N — how many cycles in the input window?** The measurements in §2.7 say the choice
   is nearly free between 25 and 50: under `window="measured"`, N=25 and N=50 remove the
   **same 18 cells** and mask 48 vs 73 of 3,375 vs 6,750 positions, because the damage sits
   at labels 12–13. N=10 removes only 2 cells. So any N from 10 to 50 is cheap, and the
   default `n_cycles=25` is a placeholder until they name one. (A model needing N > 170
   would start crossing file boundaries for the shortest cell — `EL150800460605`, 170
   segment-1 cycles — which the loader handles but which is worth knowing.)
2. **Does cycle 1 matter?** This is the whole `window="measured"` vs `window="labels"`
   decision, and it is the one place the loader's default changes the data a model sees.
   If cycle 1 must be label 1 for every cell (for a label-based feature such as the paper's
   ΔQ(100−10)), use `window="labels"` and accept that **46 of 135 cells have a structurally
   empty first position** and that `drop_invalid_cells=True` would then remove 48 cells
   instead of 18. If position *k* should mean the same amount of cycling for every cell,
   use `window="measured"` and accept that the 46 cells of 2017-05-12 are label-shifted by
   one. §2.7's measurement is the argument for `"measured"`: it yields **zero NaN** in `X`.

Nothing else is blocking. Both questions have a defensible default already in place, so
step 1–3 of §8.2 can be built before either is answered.
