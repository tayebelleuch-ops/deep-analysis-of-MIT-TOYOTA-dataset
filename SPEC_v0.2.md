# matr_clean v0.2 / v0.3 — corrected specification

**Status: Stage 0 plan. Nothing built, nothing pushed, nothing tagged, nothing uploaded.**

This supersedes DRAFT 0.2. Every count below was re-measured against the real extraction
output (`exploration/extract_out/`, read-only) and the real `within-cycle-extraction`
documents (read with `git show`). The clone that holds the extraction branch was not
switched, edited or run in; the Zenodo upload there was not disturbed.

Verification environment: `.venv` of a sibling checkout — Python 3.13.5, pandas 3.0.6,
numpy 2.5.4, h5py 3.16.0 — identical to the environment `MANIFEST_v1.1.md` records.

---

## 0. The headline correction

**v0.2.0 needs no h5py, and needs no new derived file.** Open question 1 is answered:
all six "missing" summary series *and* every validity flag are already columns of
`within_cycle_index.csv`. §2 of the draft treated this as unknown and hedged the whole
release plan on it. It is a plain CSV, 77 columns, 72.8 MB, readable by pandas alone.

**But `load_early_window` must move to v0.3.0.** The three grid curves the autoencoder and
GAN consume (`Qdlin`, `Tdlin`, `discharge_dQdV`) exist *only* inside the HDF5 files. The
draft's own escape clause ("Moves to v0.3.0 if the grid arrays are HDF5-only") applies.

So the two-step split survives, but the cut falls in a different place than the draft drew
it:

| release | contents | dependencies |
|---|---|---|
| **v0.2.0** | per-cycle exogenous table, per-cell metadata, policy conditioning, extended `describe()` | pandas + numpy; one 72.8 MB CSV |
| **v0.3.0** | the grid curves (`load_early_window`), the native series (`load_series`), `load_vdlin`, `open_batch` | adds optional `h5py`; 2.20 GB of HDF5 |

---

## 1. Where the draft is wrong or incomplete

Numbered against the draft's own sections.

### 1.1 §2 / §14 Q1 — the per-cycle table (CONFIRM → answered)

`within_cycle_index.csv` carries, per cycle, all of:

* keys and provenance: `cell_uid`, `cycle`, `segment`, `source_batch_date`,
  `source_channel`, `source_struct_index`, `source_cycle_index`, `h5_row`, `n_samples`,
  `grid_len_raw`
* status flags: `in_analysis_set`, `beyond_crossing`, `is_placeholder`, `is_series_valid`
  and all nine of its components
* **the six series v1.0 omits**: `IR_ohm`, `QCharge_Ah`, `Tavg_C`, `Tmax_C`, `Tmin_C`,
  `chargetime_min` — plus `QDischarge_Ah` as the join proof
* ~45 further per-cycle diagnostics

No derived Parquet or CSV is needed, so none is proposed and none has been created.
§3 of the draft can drop "Small, no h5py if the per-cycle table ships as CSV … (CONFIRM)".

### 1.2 §4 (EXTRACTION.md §4) omits four real columns

The real header is **77** columns. `EXTRACTION.md` §4's column list does not mention
`QDischarge_summary`, `QCharge_summary`, `policy_C1`, `policy_C2`, all of which are
present. Documentation gap in the extraction branch, listed here for the maintainer; not
edited.

### 1.3 §6 — "per-batch lazy download" is not per-cell, and `batch_date` is a trap

The draft treats the three HDF5 files as a partition of the cells. They are not.

* 140 struct rows, **135 distinct cells**. The per-file cell counts are 46 / 48 / 46 = 140.
* **Five cells live in two files.** `2017-06-30.h5` *begins* with their segment-2 rows:

  | cell | segment 1 | segment 2 |
  |---|---|---|
  | `EL150800460486` | 2017-05-12, cycles 1–1178 | 2017-06-30, cycles 1179–2159 |
  | `EL150800460514` | 2017-05-12, cycles 1–1189 | 2017-06-30, cycles 1190–1851 |
  | `EL150800460623` | 2017-05-12, cycles 1–1176 | 2017-06-30, cycles 1177–2236 |
  | `EL150800464865` | 2017-05-12, cycles 1–1226 | 2017-06-30, cycles 1227–1708 |
  | `EL150800464977` | 2017-05-12, cycles 1–1225 | 2017-06-30, cycles 1226–1433 |

* **`batch_date` in both v1.0 CSVs is the *first* segment's, on every row.** A segment-2 row
  of a continuation cell says `2017-05-12` while its data sits in
  `within_cycle_2017-06-30.h5`. Dispatching on `batch_date` therefore opens the wrong file
  and finds no such `(cell_uid, cycle)`.

  **The loader must dispatch on `source_batch_date` from the index, never on `batch_date`.**
  This is the single most dangerous trap in v0.3.0 and gets its own regression test.

  The draft's §7 line "Continuation cells: second segment carries a cycle offset
  (1176–1226)" describes the offsets correctly but omits that the segment changes *file*.

### 1.4 §7 — dtypes are incomplete

The draft says "float32 for all fields except `t` (float64)". Also true, and needed by a
reader:

| dataset | dtype | note |
|---|---|---|
| `/vdlin` | float64 | (1000,) |
| `/native/offset` | int64 | (n_cycles+1,), uncompressed, unchunked |
| `/native/{I,V,T,Qc,Qd}` | float32 | 1-D, CSR-indexed |
| `/native/t` | float64 | 1-D, CSR-indexed |
| `/grid/{Qdlin,Tdlin,discharge_dQdV}` | float32 | (n_cycles, 1000) |
| `/row/cycle` | int32 | (n_cycles,) |
| `/row/cell_uid` | **`\|S16` fixed-width bytes** | needs `.decode()`; not a str array |

Chunking is `(65536,)` on the 1-D datasets and `(64, 1000)` on the grids, gzip-4 +
byte-shuffle. Consequence worth knowing: reading one grid row decompresses a 64-row chunk
(256 KB), so a 25-cycle window costs about one chunk per cell, not 25 reads.

### 1.5 §8 — `is_series_valid`'s headline count is wrong

The draft says `is_series_valid` "Catches impossible Qdlin (48 cycles, 32 cells, 34 clean
in v1.0), the first 53 cycles of EL150800453240, and ch 8 cycle 248."

48/32/34 is the count for **one of nine components**, `series_grid_in_range`. Measured:

| quantity | measured |
|---|---|
| cycles failing **any** series check | **249**, across **97** of 135 cells |
| of which `series_grid_in_range` (impossible `Qdlin`/`Tdlin`/`dQdV`) | 48, across 32 cells; 34 flagged clean in v1.0 |
| `is_clean_cycle=True` but `is_series_valid=False` (the "disputed" set) | **171**, across **54** cells |
| `is_clean_cycle=False` but `is_series_valid=True` (the reverse) | **87** |
| both False | 78 |
| both True | 113,223 |

All of these reproduce `REPORT_v1.1.md` exactly. "ch 8 cycle 248" is real
(`EL150800460596`, 2017-06-30) but is one member of the documented 2017-06-30 cycles
246–258 event across 14 cells; as a lone example it understates the finding.

Worst observed magnitudes, for the normalization point the colleagues care about:
`Qdlin` reaches **+1,430.7 Ah** (`EL150800460511`, 2017-06-30 ch 38, cycle 247) and
**−4,030.3 Ah** (`EL150800737364`, 2018-04-12 ch 46, cycle 368) on a 1.1 Ah cell. That
same cycle 368 also carries `Tdlin_max = 523 °C`.

### 1.6 §10 vs decision 3 — a direct contradiction

§10 says `clean="series"` **drops** cycles. Decision 3 says invalid cycles in array
outputs are **masked, never dropped**. Both cannot hold for one keyword.

**Resolution, adopted below:** `clean` drops rows in **DataFrame** returns and sets the
**mask** in **array** returns. It never changes which cycles an array contains, because
dropping from a fixed-shape `(n_cells, n_cycles, …)` tensor is not expressible. Stated
explicitly in every docstring.

### 1.7 §9 — `clean="series"` collides with the shipped `load_cycles(clean: bool)`

v0.1.1 has `load_cycles(clean: bool = True)`. Turning `clean` into a tri-state across the
package would silently change `load_cycles(clean=True)` from "v1.0 `is_clean_cycle`" to
something else. **`load_cycles` keeps its boolean meaning unchanged**; it additionally
accepts `"summary"` as a synonym for `True` and `"series"` as a widening, so no existing
call changes behaviour. New functions take the tri-state.

### 1.8 §6 — the memory figure

The draft's "~3.8 GB at float32" is low. Measured: 111,868,738 native points per series.

| everything loaded | bytes |
|---|---|
| native, 5×float32 + 1×float64 | 3.13 GB |
| grid, 3×float32×1000 over 114,738 cycles | 1.38 GB |
| **total** | **4.51 GB** |

The 25-cycle early window, by contrast, is 135 × 25 × 3 × 1000 × 4 B = **40.5 MB** — the
reason it is worth a dedicated function rather than a `load_series` loop.

### 1.9 §3 — "SHA-256 of all 8 files" is not available from one place

The Zenodo payload is 8 files (`zenodo_publish.py`): the three `.h5`,
`within_cycle_index.csv`, `within_cycle_cells.csv`, `SHA256SUMS.txt`, `EXTRACTION.md`,
`LICENSE.txt`.

But `SHA256SUMS.txt` covers **six** files, of which only five are published: it also hashes
`within_cycle_index_raw.csv` (the pre-flag intermediate, deliberately not uploaded), and it
does not hash itself, `EXTRACTION.md` or `LICENSE.txt`.

So: **5 of the 8 hashes come from `MANIFEST_v1.1.md` and can be pinned now; 3 must be
recorded at publication.** The loader only ever reads 4 of the 8 (three `.h5` + the index),
so only those 4 are load-blocking. I verified all six `SHA256SUMS.txt` entries against the
files on disk: **all match.** (`within_cycle_cells.csv` has a newer mtime than the sums
file but identical content — a byte-identical re-run, consistent with the documented
reproducibility.)

### 1.10 §11 — three limitations to add

* **`nan_to_num` does nothing about the impossible values.** There is **zero NaN anywhere**
  in the nine series over all 114,738 cycles (`REPORT_v1.1.md` §8). The *only* NaN in the
  data is the grid rows of the 46 placeholders. So `np.nan_to_num` has exactly one effect:
  it converts those 46 missing rows into plausible-looking zeros. It leaves every ±1,400 Ah
  value untouched. Both halves of the colleagues' problem are real and they are separate.
* **Placeholder *native* rows hold literal `0.0`, not NaN.** The ragged datasets store the
  struct's two zeros verbatim (`V = [0., 0.]`, `t = [0., 0.]`). A reader of native series
  cannot detect a placeholder by NaN-checking at all; the flag is the only signal. Only the
  fixed-width grid rows are NaN, because two values cannot be written into a 1000-wide row.
  Verified directly: `grid/Qdlin[0]` of `EL150800460514` cycle 1 is all-NaN with no zeros.
* **`Qdlin` understates discharge capacity by a median 31.9 mAh (~3%)**, batch-dependent
  (−36.4 / −49.4 / −27.4 mAh), because `Vdlin` starts at 3.5 V, below the 3.6 V charge
  cutoff (U17). Anyone normalizing on `Qdlin[-1]` inherits a batch-correlated bias — which
  matters directly for a batch-conditioned GAN.

### 1.11 Two documentation defects in the published data (not edited)

For the maintainer, listed not applied:

* The `grid/*` datasets in **all three** files carry the attribute
  `note = "NaN on the 46 placeholder rows, whose raw length is 2"`. Only `2017-05-12` has
  any placeholder rows; in the other two files the note is false boilerplate.
* `EXTRACTION.md` §4's column list omits the four columns named in §1.2 above.

### 1.12 Confirmed as written

`Vdlin` is 3.5 → 2.0 V, 1000 points, identical in all three files, and differs from
`np.linspace(3.5, 2.0, 1000)` in exactly **15 of 1000 points by ≤4.44e-16** — one ulp,
as the draft says. Join key, cycle = struct index + 1, "struct rows are not in channel
order", the 114,738 / 113,559 / 1,179 / 46 / 135 counts, and "cycles 10 and 100 always fall
in segment 1" all verify. Every cell has segment 1 ≥ **170** cycles, so a 25-cycle window
never crosses a file.

---

## 2. Open question 1, answered in full

> Does the per-cycle table ship as CSV (so v0.2.0 needs no h5py)?

**Yes.** It is `within_cycle_index.csv`, 114,738 rows × 77 columns, 72.8 MB, and it already
contains every field `load_cycle_features` promises. v0.2.0 depends on pandas + numpy only.

**No derived file is required, and I have not created one.** For the record, if the 72.8 MB
download is later judged too heavy for a table-only release, the smallest sufficient subset
— 27 columns: keys, provenance, `h5_row`, `n_samples`, the four status flags, the nine
components, and the seven summary series — measures:

| form | size |
|---|---|
| full index, as published | 72.8 MB (gzip 21.7 MB) |
| 27-column subset, CSV | 21.5 MB (gzip 4.6 MB) |
| 27-column subset, in memory | 26.5 MB |

Hosting such a file would need: its own SHA-256 in `constants.py`, a line in a manifest, a
reproducible one-script derivation committed beside it, and a home. Since it would be
*derived from a derived dataset*, it should go in the **same Zenodo record** rather than a
second one, which means it must exist *before* publication or wait for a v2 of the record.
**Recommendation: do not ship it.** Serve the 72.8 MB index, and let callers who want the
small form slice it themselves; `pandas.read_csv(usecols=…)` on the published file gives the
same 26.5 MB in memory without a second artefact to hash, host and keep honest.

---

## 3. Module structure and public API

```
matr_clean/
  __init__.py        re-exports; __version__
  constants.py       v1.0 constants (unchanged) + the v1.1 block of §4
  _locate.py         v0.1.1 lookup order, extended to the v1.1 files (unchanged logic)
  _docs.py           @@placeholder@@ docstring filling (unchanged)
  loaders.py         v1.0 loaders (unchanged) + load_cycle_features, load_cell_features
  conditioning.py    load_conditioning  (new, v0.2.0, pandas-only)
  series.py          load_series, load_early_window, load_vdlin, open_batch  (v0.3.0)
  _h5.py             the only module that imports h5py; imported lazily
  splits.py          unchanged
```

`h5py` is imported **inside** `_h5.py` functions, never at module scope, so
`import matr_clean` works without the extra. Absent, the series functions raise
`ImportError("… needs the 'series' extra: pip install 'matr-clean[series]'")`.

### v0.2.0 — pandas + numpy only

```python
load_cycle_features(variables=None, clean="series", beyond_crossing=False,
                    include_test=False, data_dir=None) -> pd.DataFrame
```
Keyed `(cell_uid, cycle)`, one row per cycle, row order = the index's own (ascending
channel, then cycle). Columns: the seven summary series (`QDischarge_Ah`, `QCharge_Ah`,
`IR_ohm`, `Tavg_C`, `Tmax_C`, `Tmin_C`, `chargetime_min`), the v1.0 columns joined from
`analysis_set_cycles.csv` (`soh`, `cycles_to_eol`, the five v1.0 flags), the v1.1 flags
(`is_series_valid` + nine components, `in_analysis_set`, `beyond_crossing`,
`is_placeholder`), and provenance (`segment`, `source_batch_date`, `source_channel`,
`h5_row`, `n_samples`). Flag columns are **always present**, whatever `clean` drops.
`variables=` selects among the seven series; flags and keys are never droppable.
`df.attrs["filters"]` as v0.1.1, with per-reason drop counts.

```python
load_cell_features(include_test=False, data_dir=None) -> pd.DataFrame
```
`analysis_set_cells.csv` (31 columns) left-joined to `within_cycle_cells.csv`'s six new
ones: `n_segments`, `segments_resolved`, `n_cycles_total`, `policy_underscore`,
`policy_readable_as_stored`, `cycle_life_struct_field`. 135 rows either way.

```python
load_conditioning(fields=("policy_C1","policy_Q1_pct","policy_C2","policy_n_steps"),
                  include_test=False, data_dir=None) -> dict
```
Answers open question 3 at **no data cost**: `analysis_set_cells.csv` already carries all
four policy numbers. Returns `{"cell_uid": (n,) str, "X": (n, k) float32,
"fields": (...), "batch_date": (n,) str}`, aligned row-for-row with
`load_early_window`'s `cell_uid`, which is what makes it useful to a conditional GAN.
One-hot batch is the caller's business; the raw column is given.

### v0.3.0 — adds optional `h5py`

```python
load_early_window(n_cycles=25, fields=("Qdlin","Tdlin","dQdV"), window="measured",
                  clean="series", include_test=False, data_dir=None) -> dict
```

| key | shape / dtype | meaning |
|---|---|---|
| `X` | `(n_cells, n_cycles, n_fields, 1000)` float32 | as stored; **never** interpolated or zero-filled |
| `cell_uid` | `(n_cells,)` str | the row index; the alignment contract |
| `cycle` | `(n_cells, n_cycles)` int32 | **which label each position actually is** |
| `valid` | `(n_cells, n_cycles)` bool | `True` = usable under `clean` |
| `vdlin` | `(1000,)` float64 | as stored |
| `fields` | tuple | field order along axis 2 |
| `filters` | dict | the same record `df.attrs["filters"]` carries |

`clean` sets `valid`; it never changes `X`'s shape. Invalid positions keep whatever the
file holds — NaN for placeholder grid rows, the real ±1,400 Ah numbers for out-of-band
rows. **The loader does not repair them, and documents that `nan_to_num` is not a repair.**

```python
load_series(cell_uid, cycles=None, fields=("t","I","V","T"), grid=False,
            clean="series", data_dir=None) -> dict
```
Native fields are ragged, so they come back as a **list of 1-D arrays, one per requested
cycle**, in the order of the returned `cycle` array — not a padded matrix, per decision 1.
Grid fields come back `(n_cycles, 1000)`. Also returns `cycle`, `valid`, and `n_samples`.
`cycles=None` means every cycle of that cell, which for the largest cell is ~60 MB.

```python
load_vdlin(data_dir=None) -> np.ndarray          # (1000,) float64, as stored
open_batch(batch_date, data_dir=None) -> h5py.File   # mode="r", escape hatch
```
`open_batch` takes a **`source_batch_date`** and says so in its docstring, with the
continuation trap spelled out.

### Memory behaviour

* One HDF5 file open at a time; `load_early_window` groups cells by `source_batch_date`,
  opens each file once, and closes it before the next.
* Reads are per-cell slices, never whole datasets. `native/offset` (≤ 51,008 int64 =
  408 KB) is the only dataset read whole.
* Nothing is cached across calls except the index DataFrame and the two v1.0 tables
  (the existing `loaders._CACHE`). Array payloads are never cached.
* `load_early_window`'s whole return is 40.5 MB at the default; `load_series` on one cell
  peaks around 60 MB. There is no code path that materialises the 4.51 GB whole.

---

## 4. The Zenodo constants block

One block in `constants.py`, nothing Zenodo-dependent anywhere else.

```python
# --- v1.1 data: the Zenodo record -----------------------------------------
# The deposit is a DRAFT. Until it is published these three are None and
# every download path raises; data_dir / MATR_CLEAN_DATA_DIR / clone work fully.
V11_ZENODO_DOI       = None   # TODO after publication, e.g. "10.5281/zenodo.XXXXXXX"
V11_ZENODO_RECORD_ID = None   # TODO after publication
V11_ZENODO_BASE      = None   # TODO "https://zenodo.org/records/{record_id}/files"

V11_H5_FILES = {                      # source_batch_date -> filename
    "2017-05-12": "within_cycle_2017-05-12.h5",
    "2017-06-30": "within_cycle_2017-06-30.h5",
    "2018-04-12": "within_cycle_2018-04-12.h5",
}
V11_INDEX_FILE = "within_cycle_index.csv"
V11_CELLS_FILE = "within_cycle_cells.csv"

# From MANIFEST_v1.1.md. Pinned now; these are final and byte-reproducible.
V11_SHA256 = {
    "within_cycle_2017-05-12.h5": "8a789f4a83409ad0c1d6c214c836f2de94b63ef2e73a50722fe057c3d8a89d77",
    "within_cycle_2017-06-30.h5": "5f3f752d9d9a0276442fbb853941d9b212e7fffd152995b207ae6fa4a4503fae",
    "within_cycle_2018-04-12.h5": "bdd195323719986b3d77d4bd610c26e5e4e7c8d8ddde558b03b4696a2bcc6107",
    "within_cycle_index.csv":     "93176963bbaaaea60a46591a3e7d1e5c3f1a04a250107eec1b754a3311b207dc",
    "within_cycle_cells.csv":     "ebdfca86381f7a092da9dcfdb57c90a18c716957fd37080aa8c5cd208ab3147d",
}
V11_SIZE_BYTES = {   # 2.20 GB of HDF5 + 72.8 MB of index
    "within_cycle_2017-05-12.h5": 797_659_714,
    "within_cycle_2017-06-30.h5": 581_592_476,
    "within_cycle_2018-04-12.h5": 823_392_641,
    "within_cycle_index.csv":      72_846_386,
    "within_cycle_cells.csv":          14_379,
}
# Published but not loaded, so not download-blocking:
# SHA256SUMS.txt, EXTRACTION.md, LICENSE.txt -- hashes recorded at publication.
V11_DATA_TAG = None   # TODO the git tag the record corresponds to ("v1.1" proposed)
```

**While `V11_ZENODO_BASE is None`:**

* `data_dir=`, `set_data_dir()`, `MATR_CLEAN_DATA_DIR`, and the clone's
  `exploration/extract_out/` all work completely, hashes verified.
* any path that would download raises
  `DataDirError("v1.1 data not yet published; use data_dir= or MATR_CLEAN_DATA_DIR")`
  — one message, naming both routes, raised before any network call.
* `describe()` prints the v1.1 section with "not yet published (local data_dir only)".

**Filling them after publication:** set the three `TODO`s and `V11_DATA_TAG` from the
minted record; add the three remaining hashes. Nothing else changes, because no other
module mentions Zenodo.

**The test that keeps it honest** — `tests/test_manifest_hashes.py`, extended, parsing
`exploration/MANIFEST_v1.1.md` with the regex style already used for `MANIFEST.md`:
asserts every key of `V11_SHA256` / `V11_SIZE_BYTES` appears in the manifest's Outputs
table with the identical value, and that the manifest lists no loaded file the constants
omit (so a newly published file cannot be silently ignored). It skips with a clear reason
when no clone is present, as the existing test does. A second test asserts that with
`V11_ZENODO_BASE = None` every download entry point raises `DataDirError` and performs no
socket call.

**Lookup order, unchanged from v0.1.1**, with step 4 widened: `data_dir` →
`set_data_dir()` → `$MATR_CLEAN_DATA_DIR` → clone (`exploration/`, and
`exploration/extract_out/` for the v1.1 files) → cache (`~/.cache/matr_clean`).
User folders stay read-only and are verified once per process; the cache is the only place
written. Per-file lazy download, HTTP Range resume, retry with backoff — all inherited from
v0.1.1 `_locate.py`, which already does exactly this for the three CSVs.

---

## 5. Tests

**Fixture.** `tests/fixtures/make_fixture.py` (committed, deterministic) writes
`tiny_within_cycle.h5` + `tiny_index.csv`, a few KB, mirroring the real layout exactly:
`/vdlin` float64 (1000,), `/native/offset` int64, the five float32 + `t` float64 ragged
datasets, three `(n,1000)` float32 grids, `/row/cycle` int32, `/row/cell_uid` `|S16`, the
same attributes, the same gzip-4 + shuffle. It contains, by construction: a placeholder
cycle (2 native zeros, all-NaN grid row), an out-of-band `Qdlin` cycle, a continuation cell
split across two files whose `batch_date` ≠ `source_batch_date`, and a cell whose struct
index ≠ channel − 1. Committed, so the suite runs with no data present.

**Integration**, skipped unless `MATR_CLEAN_TEST_DATA` is set; pointed read-only at
`exploration/extract_out/` (or the Zenodo cache). Opens every file `mode="r"` and asserts
nothing is written — the fixture suite is what CI runs.

**Regression tests, each with the number it defends:**

| test | asserts |
|---|---|
| placeholder masked, not zero-filled | the 46 rows come back `valid=False`; `X` at those positions is NaN, **never 0.0**; `is_placeholder` survives every `clean` setting. And the native counterpart: those rows hold literal `0.0`, so the flag is the only signal |
| the `nan_to_num` pitfall | `np.nan_to_num(X)` changes **exactly** the placeholder grid positions and **no** out-of-band value — the two failures are independent |
| impossible `Qdlin` | `series_grid_in_range` fails on **48** cycles / **32** cells, **34** of them `is_clean_cycle=True`; extremes **+1430.7** and **−4030.3 Ah** |
| the full 2×2 | 171 disputed / 87 reverse / 78 both-false / 113,223 both-true on 113,559 analysis-set rows |
| `is_series_valid` totals | **249** cycles across **97** cells — guards against the draft's 48-for-249 conflation |
| row counts | 114,738 index rows; 113,559 `in_analysis_set` = `len(analysis_set_cycles.csv)`; 1,179 `beyond_crossing`; 46 placeholders; 135 cells; `(cell_uid, cycle)` unique |
| join integrity | index ⋈ `analysis_set_cycles.csv` on `(cell_uid, cycle)` validates `1:1`; `QDischarge_Ah` equals `QD_Ah` **bit-for-bit** on all 113,559 shared rows |
| **addressing is never positional** | for a cell whose `source_struct_index ≠ source_channel − 1`, every accessor returns the channel-resolved row; a deliberately position-addressed lookup returns different data and the test asserts they differ. Mirrors `exploration/test_cell_addressing.py` |
| continuation dispatch | segment-2 cycles of all five cells resolve through `source_batch_date`; a lookup dispatched on `batch_date` is asserted to fail, so the trap can never regress silently |
| `vdlin` as stored | 15 of 1000 points differ from `np.linspace(3.5, 2.0, 1000)`, max 4.44e-16; the loader never reconstructs it |
| dtypes as stored | `t` float64, other eight float32, `vdlin` float64, `cycle` int32, `cell_uid` decoded from `\|S16` |
| masks vs drops | `clean=` drops rows in DataFrame returns and only flips `valid` in array returns; `X.shape` is identical under all three settings |
| flags always present | every flag column survives `variables=` and every `clean=` |
| `clean` compatibility | `load_cycles(clean=True)` is byte-identical to v0.1.1's output |
| early window | `n_cycles=25` under both conventions; 93 invalid positions across 48 cells under `window="labels"`; `EL150800453240` entirely masked |
| no writes | the integration run leaves every mtime and size unchanged |

**Matrix.** pandas 2.x and 3.x × two h5py versions (the 3.16.0 that wrote the files, and
the oldest supported — **floor `h5py>=3.0`**: the files use only gzip + shuffle and plain
datasets, so no newer feature is needed; the floor is *tested*, not asserted). The
Python 3.9 floor is checked statically, as now — `python3.9 -m compileall` plus a grep for
3.10+ syntax; the package already avoids `match`, `X | Y` annotations and `dict |`.
`pyproject.toml` gains `[project.optional-dependencies] series = ["h5py>=3.0"]`.

---

## 6. "The first 25 cycles" — what it means, and the default

Measured over segment 1 of all 135 cells (every cell has ≥170 segment-1 cycles, so the
window never crosses a file):

| batch | cells | rows with label 1–25 | placeholders | series-invalid |
|---|---|---|---|---|
| 2017-05-12 | 46 | 1,150 | **46** (one per cell, label 1) | **85** |
| 2017-06-30 | 43 | 1,075 | 0 | 0 |
| 2018-04-12 | 46 | 1,150 | 0 | 8 |

So the two conventions differ **only for the 46 cells of 2017-05-12**:

* `window="labels"` → labels 1…25. Position 0 is the placeholder for those 46 cells:
  always masked, no data.
* `window="measured"` → the first 25 rows with `is_placeholder=False`, i.e. labels
  **2…26** for those 46 cells and 1…25 for the other 89.

**Recommended default: `window="measured"`**, with `window="labels"` available.

Reasoning: for an autoencoder or GAN over a 25-step window, position *k* should mean the
same amount of cycling for every cell. Under `"labels"`, position 0 is structurally empty
for a third of the cells, so a third of the batch carries a guaranteed-masked first step —
precisely the hole `nan_to_num` turned into a zero. `"measured"` gives all 135 cells 25
real measurements.

**The cost, stated loudly in the docstring and USAGE.md:** under `"measured"` the cycle
*labels* of the 2017-05-12 cells are shifted by one, so position 9 is label 10 for 89 cells
and label 11 for 46. That breaks the paper's ΔQ(100−10) convention, which is label-based
(`REPORT_v1.1.md` §6 computes it on labels 10 and 100). Two mitigations, both adopted:
the returned dict **always** carries the `cycle` label matrix, so what you got is never
ambiguous; and label-indexed features should use `load_series(cell, cycles=[10, 100])`,
where the caller names labels explicitly, not `load_early_window`.

**What the window actually contains — the finding the colleagues need most.** Under
`window="labels"`, **93 of the 3,375 positions are series-invalid, across 48 of 135 cells**:

* 46 placeholders (label 1 of every 2017-05-12 cell) — all-NaN grid rows;
* **`EL150800453240`: all 25 of its first 25 cycles**, inside the U15 splice run
  (cycles 1–53). This cell contributes nothing usable to a 25-cycle model and must be
  masked wholesale, not averaged in;
* a cluster at labels **12–13** across 18 cells — the documented 2017-05-12 multi-cell
  event, 40 of the 46 cells of that batch carry one;
* **6 positions with impossible `Qdlin`**, inside the first 25 cycles: labels 12–13 of
  `EL150800464977` (up to **+45.3 Ah**), `EL150800464865` (**+48.8 Ah**),
  `EL150800464002` (**+31.0 Ah**), `EL150800463871` (**+33.0 Ah**),
  `EL150800460514`, and `EL150800737364`.

Those last six are the ones that wreck a normalization fitted on this window: ~45 Ah
against a 1.1 Ah nominal, inside the data the GAN is conditioned on. `is_series_valid`
catches all six, and `is_clean_cycle` does not catch five of them.

Window selection is **structural only** — by label, or by measured-ness. It is never by
validity, because that would make the window's physical span depend on data quality and
would collide with decision 3. Validity is always the mask.

---

## 7. Decisions, carried forward

1. No resampling; grid fields as stored, native fields as stored (ragged lists).
2. Default drops series-invalid and placeholder cycles **in DataFrame returns**;
   `clean=False` returns everything; `clean="summary"` is v1.0 `is_clean_cycle` only.
   Drop counts in `df.attrs["filters"]` and `describe()`. Cycle and flag columns always kept.
3. Array returns **mask**, never interpolate, zero-fill or drop.
4. Join key `(cell_uid, cycle)`; cycle = struct index + 1; never row position — and, new,
   never dispatch files on `batch_date`.
5. Test fold (−1) excluded unless `include_test=True`; `cv_splits` unchanged.
6. Two releases, with the cut at §0: v0.2.0 = CSV-only table + conditioning;
   v0.3.0 = HDF5 series **and the early window**.

---

## 8. Open questions

| # | question | status |
|---|---|---|
| 1 | per-cycle table as CSV? | **answered: yes, `within_cycle_index.csv`. No h5py, no derived file** |
| 2 | early-window convention | **answered: recommend `window="measured"`, `"labels"` by argument** (§6) |
| 3 | policy-conditioning helper | **answered: yes, free — `analysis_set_cells.csv` already has `policy_C1/Q1_pct/C2/n_steps`. Proposed as `load_conditioning`** |
| 4 | ΔQ(100−10) helper | **defer.** Needs grid data, so v0.3.0 at the earliest; not needed for the GAN. If built, validate against `REPORT_v1.1.md` §6: ρ = −0.9200 (128 cells), −0.9274 (`in_paper_124`), and per-batch −0.945 / −0.815 / −0.785 (U19) |
| 5 | Colab for 2.3 GB | **recommend Drive copy as the documented default**, per-batch download as the alternative; both in USAGE.md. One batch (0.6–0.8 GB) re-downloads per runtime acceptably; 2.3 GB does not |
| 6 | which teammates need which fields | **still open — needs the team.** Blocks nothing in v0.2.0; decides whether v0.3.0's `load_series` needs more than `("t","I","V","T")` by default |

---

## 9. What I could not confirm

* **The Zenodo DOI, record ID, file URLs and publication date.** The deposit is a draft, as
  stated. Hence the `None`/`TODO` block in §4. The draft's §3 "Zenodo deposit published …
  SHA-256 of all 8 files [PENDING]" stays PENDING, and §1.9 above says which 5 of the 8 can
  be pinned regardless.
* **The hashes of `SHA256SUMS.txt`, `EXTRACTION.md` and `LICENSE.txt`** as published —
  nothing hashes them today. Not load-blocking.
* **The v1.1 merge and tag.** `v1.1` is a proposed name, not a tag
  (`MANIFEST_v1.1.md`, open decision 3). Note for whoever merges:
  **`within-cycle-extraction` is not a descendant of `main`.** It branched at `09f1964`
  (the v0.1.0 loader merge), so `main`'s v0.1.1 retry/resume work and
  `tests/test_download_retry.py` are absent from it. A naive `diff main..within-cycle-extraction`
  reads as if that work were deleted; it is not. The merge needs a real merge, not a
  fast-forward, and `_locate.py` is the file that will conflict.
* **Whether `is_clean_cycle` stays as it is.** `MANIFEST_v1.1.md` open decision 1 offers
  either adding `is_series_valid` alongside (recommended there, and what this plan assumes)
  or applying the 171 corrections. **If the corrections are applied instead,
  `analysis_set_cycles.csv` changes and its SHA-256 changes**, which breaks `constants.SHA256`
  and the `v1.0` pin in shipped v0.1.x installs. That is a release-ordering dependency, not
  just a data question, and it should be settled before v0.2.0 is tagged.
* **The h5py floor, empirically.** `h5py>=3.0` is my reasoned proposal from the features the
  files use; it is not yet tested against an actual old h5py. §5 makes that a test, not an
  assertion.
* **A fresh Colab run.** Not attempted; no large file is downloadable yet.

## 10. What the notebook use case still cannot get

* **Grid curves before v0.3.0.** `Qdlin`, `Tdlin` and `discharge_dQdV` are HDF5-only, so
  the autoencoder/GAN input itself arrives with v0.3.0. v0.2.0 gives the conditioning
  (policy, batch, IR, temperatures, charge time) and the per-cycle masks, which is enough
  to build and validate the data pipeline against the real flags before the 2.3 GB lands.
* **Wall-clock time, at all.** `t` resets to exactly 0.0 each cycle and no struct carries a
  date. Rests and gaps between cycles are unrecoverable. Nothing in any release can fix
  this; U14's clustering is explicitly "consistent with" rather than "shows".
* **Padded/stacked native series.** By decision 1 `load_series` returns ragged lists.
  Anything wanting `(n_cycles, max_len)` must pad itself — deliberately, so the padding
  value is the caller's visible choice and never a silent zero.
* **A cross-batch guarantee.** The batches are not exchangeable (CV cutoff C/50 vs C/20,
  different rests, a ~1.4 C baseline offset in 2018-04-12, and `Qdlin`'s 3% bias varying
  −27 to −49 mAh by batch). `cv_splits("batch")` exists for this; a conditional GAN should
  take `batch_date` as a conditioning variable, not hope it averages out. U19 quantifies the
  cost of ignoring it: ρ = −0.925 pooled against −0.785 within the weakest batch.
