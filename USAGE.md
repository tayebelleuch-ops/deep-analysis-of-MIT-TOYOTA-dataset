# Using `matr_clean`

A small Python package that hands you the cleaned MIT–Stanford–TRI battery analysis
set as two pandas DataFrames. It needs **pandas and numpy only** — no `h5py`, and none
of the multi-gigabyte raw `.mat` files.

```bash
pip install -e .                 # from a clone
```

```python
import matr_clean as mc

mc.describe()        # what every default excludes, counted from the data
```

`describe()` is the fastest way to see what you are getting: 135 physical cells, 128
of them with an 80%-SOH label, 113,559 cycles truncated at each cell's 0.88 Ah
crossing, and exactly which rows each default drops — the default `load_cycles()` call
returns 90,314 of those cycles, and `describe()` says why.

The audit behind the data, and the decisions D0–D5 that shape it, are in
[`exploration/REPORT.md`](exploration/REPORT.md). This package applies those
decisions; it does not revisit any of them.

---

## Where the data comes from

The package never carries the CSVs inside it. It looks for them in this order, and the
**first match wins**:

| | source |
|---|---|
| 1 | an explicit `data_dir=` argument |
| 2 | a directory passed to `set_data_dir(path)` earlier in the session |
| 3 | the `MATR_CLEAN_DATA_DIR` environment variable |
| 4 | the repository's `exploration/` folder, when you are in a clone |
| 5 | `~/.cache/matr_clean`, downloaded once from URLs pinned to the `v1.0` tag |

Three files are required, with exactly these names:

```
analysis_set_cells.csv
analysis_set_cycles.csv
cell_inventory.csv
```

Every file is checked against the SHA-256 recorded for the `v1.0` tag before it is
used. If a directory you named holds a changed or misnamed file the loader **raises**
— it never quietly falls back to a different copy. Nothing is ever written outside the
cache: a folder you point at, and the repository's own `exploration/`, are read-only as
far as this package is concerned.

---

## Five examples

### 1. Load the labels

```python
import matr_clean as mc

labels = mc.load_labels()                    # 102 cells: labelled, minus the held-out ones
print(labels[["cell_uid", "batch_date", "policy_canonical",
              "cycle_life_cycles", "eol_basis"]].head())

print(labels["cycle_life_cycles"].describe())
print(labels["eol_basis"].value_counts())
```

The target is `eol_cycle_80pct_soh` (also returned as `cycle_life_cycles`): the cycle
at which the cell crosses 0.88 Ah = 80% of the 1.1 Ah nominal capacity (decision D0).
`eol_basis` says how it was obtained — `strict_crossing_below_0.88Ah` for a measured
crossing, `test_terminated_at_criterion` where the test stopped at the criterion and
the label is the last recorded cycle, within one cycle of the crossing.

Never use the raw struct field `cycle_life`: for 90 of the 135 cells it is the record
length plus one, not a measurement (`REPORT.md` §5).

### 2. Load the trajectories

```python
cells, cycles = mc.load_trajectories()       # 104 cells, 83,170 clean cycles

print(cycles[["cell_uid", "cycle", "QD_Ah", "soh", "cycles_to_eol"]].head())
print(cells.attrs["filters"]["excluded"])    # exactly what was dropped, and how many
```

`load_trajectories` returns the cells marked `use_for_trajectory` — everything except
the five continuation cells, where a test interruption injects 1.4–5.0% of the cell's
whole degradation range into a single cycle, in the wrong direction (decision D3).
Those five are still fine for crossing-time work; load them with `mc.load_cells()`.

Add `labelled_only=True` for the cells that also carry a target.

### 3. Fold cross-validation

```python
cells, cycles = mc.load_trajectories()

for split in mc.cv_splits("fold"):
    train = cycles[cycles["cell_uid"].isin(split.train)]
    test = cycles[cycles["cell_uid"].isin(split.test)]
    print(split.label, split.n_train, split.n_test, len(train), len(test))
    # fit on train, score on test
```

Five folds, stored in the data and fixed on 2026-10-27 (seed 20261027, stratified on
batch and label presence). Splits are **grouped by barcode**, so a physical cell —
including both segments of a continued one — can never appear on both sides.

`cv_splits` yields `Split(kind, label, train, test)`, where `train` and `test` are
sorted arrays of `cell_uid`. Filter with `.isin(...)`; never slice by row position.

**What this split does and does not test.** It only tests new *cells* from batches and
policies the model has already seen: every fold contains cells from all three batches,
and a policy is usually spread across folds. A good score here says nothing about a new
batch or a new charging policy — for those, use the next two.

### 4. Leave one batch out

```python
for split in mc.cv_splits("batch"):
    print(split.label, "->", split.n_test, "cells held out")
```

Three splits, one per `batch_date`. The batches differ in CV cutoff current, rest
scheme, end-of-life criterion and baseline temperature (`REPORT.md` §8), so this is the
honest test of cross-batch transfer. Leave one *policy* out the same way:

```python
for split in mc.cv_splits("policy"):         # 60 splits
    ...
```

60, not 69: the other nine policies appear only among the held-out test cells, so they
cannot be held out again.

### 5. The held-out test cells, once

```python
mc.load_cycles()                        # 90,314 rows — clean, held-out cells dropped
mc.load_labels()                        # 102 cells — held-out cells dropped
mc.load_cells()                         # 135 cells — the inventory view

mc.load_cycles(include_test=True)                  # 113,394 clean rows
mc.load_cycles(include_test=True, clean=False)     # 113,559 — the whole table
mc.load_labels(include_test=True)                  # 128 — all labelled cells

cells, cycles = mc.load_trajectories(include_test=True)   # 130 cells
splits = list(mc.cv_splits("fold", include_test=True))    # 6: folds 0-4, then -1
print(splits[-1].label, splits[-1].n_test)                # -1 27
```

27 of the 135 cells carry `fold == -1`. They are the fixed held-out test set and must
not be used for training or model selection, so **every loader that returns cycles,
and every split, excludes them by default** — `load_cycles`, `load_trajectories`,
`load_labels` and `cv_splits`. The one exception is `load_cells`: it is the inventory
view, one row per cell with no cycles to leak, and returns all 135 unless you pass
`include_test=False` (108). Every frame records which of these applied:

```python
cells.attrs["filters"]
# {'function': 'load_trajectories.cells', 'applied': {...},
#  'excluded': ['cells with use_for_trajectory == False ...: 5 cells', ...],
#  'n_rows_in': 135, 'n_rows_out': 104, 'data_tag': 'v1.0', ...}
```

---

## Why the loaders return different numbers of cells

Three different counts are all correct, because each answers a different question.
`REPORT.md` and `MANIFEST.md` describe **the data as published**; the loaders apply
**the modelling defaults** on top of it.

| call | cells | what it is |
|---|---|---|
| `load_cells()` | **135** | the inventory: every physical cell in the analysis set |
| `load_labels()` | **102** | labelled cells you may train on |
| `load_labels(include_test=True)` | **128** | every labelled cell — the number in `REPORT.md` |
| `load_cycles()` | 90,314 rows over **108** cells | clean cycles, held-out cells dropped |

The 135 → 128 → 102 steps are two separate subtractions:

```
135  cells in the analysis set                    load_cells()
 −7  censored: stopped above 0.88 Ah, so no label observed (decision D4)
=128  labelled cells                              load_labels(include_test=True)
−26  of the 27 held-out test cells (fold == −1); the 27th is one of the censored
=102  labelled, trainable cells                   load_labels()
```

So **102 is not a disagreement with `REPORT.md`'s 128** — it is 128 minus the
held-out test cells. The audit documents the dataset; the loader defends a model.
`load_cells()` is the one loader that keeps all 135: it is one row per cell with no
cycles to leak, so there is nothing to protect.

**An inner join silently drops the test cells.** Because the defaults differ per
loader, joining two default frames gives you the intersection, not an error:

```python
cells  = mc.load_cells()                 # 135 cells (test cells included)
labels = mc.load_labels()                # 102 cells (test cells excluded)
cycles = mc.load_cycles()                # 108 cells (test cells excluded)

len(cells.merge(cycles, on="cell_uid")["cell_uid"].unique())    # 108, not 135
len(labels.merge(cycles, on="cell_uid")["cell_uid"].unique())   # 102, not 135
```

That is usually what you want — and it is why `load_cells()` returning 135 is safe.
But it means a `cells`-based count printed next to a joined frame will not match. If
you want the counts to line up, be explicit: pass `include_test=False` to
`load_cells()` (108), or `include_test=True` to both sides (135 / 128), and never
infer the exclusion from a row count alone. Every frame records what was applied:

```python
labels.attrs["filters"]["excluded"]
# ['cells with has_eol_label == False (censored, decision D4): 7 cells',
#  'held-out test cells (fold == -1): 26 cells']
```

---

## Colab

No clone, no raw data, nothing to upload:

```python
!pip install -q "git+https://github.com/tayebelleuch-ops/deep-analysis-of-MIT-TOYOTA-dataset.git@loader-v0.1.1"
```

```python
import matr_clean as mc

mc.describe()                        # downloads the three CSVs on first use (~11 MB)
cells, cycles = mc.load_trajectories()
```

The first call downloads the three CSVs into `~/.cache/matr_clean` from URLs pinned to
the `v1.0` tag, verifies their SHA-256, and uses them for the rest of the session.
Later calls read the cache.

**The cache resets with the runtime.** A Colab runtime that is recycled or factory-reset
loses `~/.cache`, so the next session downloads the files again — about 11 MB, a second
or two. To avoid re-downloading, keep the three files in your Drive and use
`set_data_dir` (next section).

**Offline, or if the download fails,** the error lists the three URLs. Download them by
hand, put all three in one folder keeping the exact filenames, and either

```python
mc.set_data_dir("/content/matr_data")
```

or set `MATR_CLEAN_DATA_DIR=/content/matr_data` before importing.

> `loader-v0.1.1` is the tag for this loader release. Use the **loader** tag here, not
> `v1.0`: `v1.0` tags the audit and its data files and does not contain this package.
> The three CSVs are still fetched from URLs pinned to `v1.0`, which has not moved.

---

## Google Drive

Keep the three CSVs in Drive and the loader reads them straight out of the mounted
folder — no download, no cache, and it survives a runtime reset.

```python
from google.colab import drive
drive.mount('/content/drive')
```

```python
import matr_clean as mc

mc.set_data_dir('/content/drive/MyDrive/matr_clean_data')
cells, cycles = mc.load_trajectories()
```

The folder must contain exactly these three files, with these names:

```
/content/drive/MyDrive/matr_clean_data/analysis_set_cells.csv
/content/drive/MyDrive/matr_clean_data/analysis_set_cycles.csv
/content/drive/MyDrive/matr_clean_data/cell_inventory.csv
```

A browser that has already downloaded one of them once will name the second copy
`analysis_set_cycles (1).csv`; the loader needs the plain name and its error message
will tell you which file to rename.

**If the folder was shared with you, add a shortcut first.** A shared folder does not
appear under `MyDrive` until you put a shortcut to it there — mounting Drive alone will
not reveal it, and the path above will not exist. In Drive: **Shared with me** → right-click
the folder → **Organise** → **Add shortcut** → choose **My Drive**. Then remount (or
`drive.mount('/content/drive', force_remount=True)`) and the path becomes
`/content/drive/MyDrive/<folder name>`. Without the shortcut the only other route is
`/content/drive/.shortcut-targets-by-id/<id>/...`, which is not stable.

**The loader only ever reads this folder.** It does not write, move, rename or delete
anything in it, so pointing it at a shared or read-only folder is safe. It does check
each file's SHA-256 and will raise rather than load a file that has been edited.

---

## The per-cycle exogenous variables (v0.2.0)

`load_cycle_features()` returns the six per-cycle summary series the three v1.0 CSVs
never carried — internal resistance, charge capacity, the three temperatures and charge
time — one row per cycle, keyed `(cell_uid, cycle)`.

```python
import matr_clean as mc

feats = mc.load_cycle_features()
feats[["cell_uid", "cycle", "IR_ohm", "QCharge_Ah", "Tavg_C", "Tmax_C",
       "chargetime_min"]].head()
```

It still needs **only pandas and numpy**. The v1.1 release stores these in
`within_cycle_index.csv`, a plain CSV, so nothing here imports `h5py`. Only the nine
within-cycle *series* and the three voltage-grid curves live in HDF5, and those arrive
in v0.3.0.

Pick columns with `variables=`; keys and every quality flag come back regardless.

```python
ir = mc.load_cycle_features(variables=("IR_ohm", "Tmax_C"))
```

**Worked example — resistance growth over life, per batch:**

```python
feats = mc.load_cycle_features()
first = feats.groupby("cell_uid")["IR_ohm"].transform("first")
feats["ir_ratio"] = feats["IR_ohm"] / first
print(feats.groupby("source_batch_date")["ir_ratio"].describe()[["50%", "max"]])
```

**Worked example — charge time against the policy's own first-step rate:**

```python
feats = mc.load_cycle_features(variables=("chargetime_min",))
cells = mc.load_cell_features()[["cell_uid", "policy_C1", "policy_canonical"]]
joined = feats.merge(cells, on="cell_uid")
print(joined.groupby("policy_C1")["chargetime_min"].median())
```

`load_cell_features()` is `analysis_set_cells.csv` widened by the six per-cell columns
the extraction adds, `n_segments` and `segments_resolved` among them.

### Conditioning arrays for a generative model

`load_conditioning()` hands you the charging policy as a numeric matrix aligned
row-for-row with `cell_uid`, which is what a conditional autoencoder or GAN needs:

```python
cond = mc.load_conditioning()
cond["X"].shape        # (n_cells, 4) float32: C1, Q1_pct, C2, n_steps
cond["cell_uid"]       # the alignment contract
cond["batch_date"]     # keep this as a factor -- the batches are not exchangeable
```

This one reads `analysis_set_cells.csv` alone, so it works **before** any v1.1 file is
present. `include_cycle_counts=True` adds per-cell `n_cycles` and `n_series_invalid`
from the index, and does need it.

`X` is float32 and may contain `NaN` where a policy string does not parse into a field.
Check with `np.isnan(cond["X"]).any(axis=0)` before fitting a scaler — nothing here
imputes.

---

## `data_dir` vs `v11_dir`

Two arguments, because in a clone the two file sets live in **different folders**:

| argument | names | default lookup |
|---|---|---|
| `data_dir` | the three v1.0 CSVs | `exploration/` |
| `v11_dir` | `within_cycle_index.csv`, `within_cycle_cells.csv` | `exploration/extract_out/` |

In a clone you pass neither and both are found. If you keep everything in one folder,
`data_dir=` alone is enough — `v11_dir` falls back to `data_dir` when that directory
holds the v1.1 files, then to the ordinary lookup order. If they are in separate places,
name both:

```python
mc.load_cycle_features(data_dir="~/matr/csv", v11_dir="~/matr/within_cycle")
```

The lookup order is v0.1.1's, unchanged: argument → `set_data_dir()` →
`$MATR_CLEAN_DATA_DIR` → clone → `~/.cache/matr_clean`, downloaded once from the
Zenodo record if it is not there. A directory you name explicitly **raises rather than
falling back** — a wrong path is a mistake worth seeing. Every file is checked against
the SHA-256 in `MANIFEST_v1.1.md` once per process, and your folders are only ever
read.

### The v1.1 data comes from a published Zenodo record

The within-cycle extraction is published, with a DOI, so step 5 works for it exactly
as it does for the v1.0 CSVs:

| | |
|---|---|
| record | <https://zenodo.org/records/23984188> |
| version DOI | `10.5281/zenodo.23984188` — what the loader pins |
| concept DOI | `10.5281/zenodo.23984187` — resolves to "latest"; **not** used |
| published | 2026-11-05 (version label `1.1.0`) |

The *version* DOI is pinned deliberately. A concept DOI follows whichever version is
latest, so pinning it would let a future revision of the record change what your code
loads without a line of your code changing.

**Only what you ask for is downloaded.** The two CSVs are 72.9 MB together, and that is
all the DataFrame loaders need; the three HDF5 files are 2.20 GB and are fetched a
batch at a time, when something asks for that batch — which nothing does yet, because
the code that *reads* the HDF5 is still to come. Files land in
`~/.cache/matr_clean` (or `$MATR_CLEAN_CACHE_DIR`), are staged through a `.part` file so
an interrupted download cannot be mistaken for a finished one, and are checked against
the SHA-256 in `MANIFEST_v1.1.md` before they are used. A file in the cache that fails
that check is **deleted**, so the next run refetches it rather than reading bad bytes
forever; a file in a directory *you* named is never deleted, only reported.

If the network is unavailable the loader says so once, without retrying — a refused
connection is not a transient failure — and prints the per-file URLs, their sizes and
both of the routes that need no network:

```
The v1.1 within-cycle data is not available locally and could not be downloaded.
  reason: within_cycle_index.csv: <urlopen error [Errno 111] Connection refused>

It is published, with a DOI, at
  https://zenodo.org/records/23984188
  DOI 10.5281/zenodo.23984188  (version 1.1.0)
...
```

Every Zenodo-dependent value lives in one block of `matr_clean/constants.py`
(`V11_ZENODO_*`, `V11_DATA_TAG`), read out of the record's own files API listing rather
than assembled from a URL pattern — Zenodo serves a file's bytes from
`…/files/<name>/content` and its *metadata* from `…/files/<name>`, and only the listing
says which is which. Blank that block and the package returns to its pre-publication
behaviour: everything local keeps working and every download path raises
`v1.1 data not yet published; use data_dir= or MATR_CLEAN_DATA_DIR.` before any socket
call.

Of the record's eight files, five carry a published SHA-256 and four are ever loaded.
`SHA256SUMS.txt` covers six files of which five are published: it also hashes
`within_cycle_index_raw.csv`, the pre-flag intermediate that is deliberately not
uploaded, and it does not hash itself, `EXTRACTION.md` or `LICENSE.txt`. Zenodo reports
an MD5 for all eight; the five that matter are in `constants.V11_ZENODO_MD5`, which is
what you can compare against the record page without downloading anything.

---

## Two quality flags, two different questions

| flag | asks | window |
|---|---|---|
| `is_clean_cycle` (v1.0) | is this cycle's **capacity** consistent with its neighbours? | 11-cycle rolling median on `QDischarge`, plus `chargetime` and seam proximity |
| `is_series_valid` (v1.1) | is this cycle's **own trace** intact? | one cycle, nine checks, no rolling window |

**Neither supersedes the other, and they disagree in both directions.** On the 113,559
analysis-set rows:

```
                 series-invalid   series-valid
  unclean                   78             87
  clean                    171        113,223
```

The 171 are the ones that matter: clean by every summary-level check, yet failing on
their own trace. They span 54 cells. `is_series_valid` fails on **249 cycles across 97
of the 135 cells** in total — that is the figure to quote, not the 48/32/34 of its
`series_grid_in_range` component alone.

**No v1.0 file or flag is edited.** The 171 proposed corrections are published as a
table (`exploration/tables/v11_proposed_clean_cycle_corrections.csv`) and applied
nowhere; the v1.0 hashes stay pinned.

### `require_series_valid`

`load_cycle_features` applies **both** flags by default. `load_cycles` keeps its v0.1.1
behaviour exactly and takes the series filter as a separate argument:

```python
mc.load_cycles()                             # v0.1.1, unchanged: is_clean_cycle only
mc.load_cycles(require_series_valid=True)    # + the v1.1 flag, removes 171 more rows
mc.load_cycle_features()                     # both, by default
mc.load_cycle_features(clean=False)          # the series flag alone
mc.load_cycle_features(clean=False, require_series_valid=False,
                       beyond_crossing=True, include_test=True)   # all 114,738
```

It is a separate argument rather than a third value of `clean` precisely because the two
are not nested: folding them together would have silently redefined `clean=True` for
every call already written. Passing `require_series_valid=True` to `load_cycles` makes it
need the v1.1 index, so a call that worked with the three CSVs alone can start needing a
download.

Every call records what it dropped:

```python
feats = mc.load_cycle_features()
for reason in feats.attrs["filters"]["excluded"]:
    print(reason)
# cycles past the 0.88 Ah crossing (beyond_crossing): 1179 rows
# cycles of held-out test cells (fold == -1): 23100 rows
# cycles v1.0 flagged (is_clean_cycle == False): 145 rows
# cycles failing is_series_valid: 152 rows (of which 152 are is_clean_cycle == True)
```

`mc.describe()` prints the same accounting, counted live.

---

## Masks and gaps

**Dropped cycles leave gaps, and the loader never fills them.** Nothing is
interpolated, padded, renumbered, forward-filled or smoothed. The `cycle` column is
always kept, so the holes are visible:

```python
feats = mc.load_cycle_features()
one = feats[feats["cell_uid"] == "EL150800737364"]["cycle"].to_numpy()
import numpy as np
print(np.where(np.diff(one) > 1)[0].size, "gaps")   # the dropped cycles
```

Gap filling is **your** choice, and it should be a deliberate one: a model over
consecutive cycles and a model over cycle *number* want different things. If you need a
dense index, reindex explicitly so the fill value is in your code and not in ours:

```python
dense = (one_cell.set_index("cycle")
                 .reindex(range(1, int(one_cell["cycle"].max()) + 1)))
```

In v0.3.0 the array-returning functions follow the same principle differently: a
fixed-shape `(n_cells, n_cycles, …)` tensor cannot drop a row, so invalid cycles come
back **masked** — a boolean `valid` array alongside the data — never interpolated and
never zero-filled. `clean=` drops rows in DataFrame returns and sets the mask in array
returns. The data at a masked position is whatever the file holds.

---

## If you use `np.nan_to_num`, read this

Two separate problems, and `nan_to_num` addresses neither correctly.

**1. There is almost no `NaN` in this data.** Across all 114,738 cycles there is
**zero** `NaN` in any of the nine within-cycle series. The only `NaN` anywhere is the
grid rows of the **46 placeholder cycles** — 2017-05-12's cycle 1, one per cell, which
the source structs record as two zeros rather than a measurement. The extraction writes
those fixed-width grid rows as `NaN` deliberately, *so that a reader who ignores the
flags gets an obviously missing value rather than a plausible one*.

`np.nan_to_num` undoes exactly that safeguard: it turns 46 missing cycles into
0.0-valued cycles that look like real measurements of a dead cell. Filter on
`is_placeholder` or `is_series_valid` instead.

Worse, in the **native** (ragged) series the placeholders hold **literal `0.0`**, not
`NaN` — `V = [0., 0.]`, `t = [0., 0.]`. So NaN-checking cannot detect them there at
all. The flag is the only signal.

**2. `nan_to_num` does nothing about the impossible values.** On 48 cycles across 32
cells the interpolated grid curves leave the physically possible band, `Qdlin` reaching
**+1,430.7 Ah** (`EL150800460511`, cycle 247) and **−4,030.3 Ah**
(`EL150800737364`, cycle 368) on a **1.1 Ah** cell — and `Tdlin` reaching 523 °C on the
latter. These are finite floats. `nan_to_num` passes them straight through, and any
scaler fitted on them is ruined. **34 of the 48 are `is_clean_cycle == True`**, so the
v1.0 flag will not save you; `series_grid_in_range` and `is_series_valid` will.

**Inside the first 25 cycles** — the window an early-cycle model consumes — labels 1–25
hold **93 invalid positions across 48 of the 135 cells**: the 46 placeholders, a cluster
at labels 12–13 from an undocumented multi-cell event, **6 positions with impossible
`Qdlin` (up to +48.8 Ah)**, and `EL150800453240`, **all 25 of whose first 25 cycles** are
inside a 53-cycle splice run. That cell contributes nothing usable to a 25-cycle model
and should be masked wholesale.

```python
feats = mc.load_cycle_features(clean=False, require_series_valid=False,
                               include_test=True)
window = feats[(feats["segment"] == 1) & (feats["cycle"] <= 25)]
bad = window[~window["is_series_valid"]]
print(len(bad), "invalid positions across", bad["cell_uid"].nunique(), "cells")
```

### The early-cycle window, in v0.3.0

`load_early_window(n_cycles=25)` will default to `window="measured"`: the first 25
cycles with `is_placeholder == False`, so position *k* means the same amount of cycling
for every cell. For the 46 cells of 2017-05-12 that is labels **2–26**; for the other 89
it is 1–25. `window="labels"` gives labels 1…N instead, with the placeholder returned
and masked.

The return **always** carries the `cycle` label matrix, so which labels you got is never
ambiguous. That matters because the paper's ΔQ(100−10) feature is **label**-based: for
label-indexed work use `load_series(cell, cycles=[10, 100])`, where you name the labels,
not `load_early_window`.

---

## The large files, Colab and Drive (v0.3.0)

v0.2.0 downloads nothing new: the per-cycle index is 72.8 MB and the v1.0 CSVs are
11 MB. v0.3.0 adds **2.20 GB** of HDF5 — three files of 0.6–0.8 GB, one per batch.

**Recommended on Colab: a Drive copy.** A Colab runtime is discarded, so a per-session
download of 2.3 GB is a recurring cost; Drive is paid once.

```python
from google.colab import drive
drive.mount("/content/drive")

import matr_clean as mc
mc.load_cycle_features(v11_dir="/content/drive/MyDrive/matr/within_cycle")
```

Keep the files in a plain Drive folder, not a zip: the loader reads them in place and
never writes to a folder you name. Hashes are verified once per process, which on 2.2 GB
over Drive takes a few seconds — worth it once per session.

**The alternative is a per-batch download.** Only the batches you touch are fetched, so
a model that uses one batch pays 0.6–0.8 GB rather than 2.3 GB. The download route is
in place and pinned to the published record; what is still to come is the code that
*reads* the HDF5, which is why the figures below are the only thing this section can
quote today.

A cell can span **two** batch files (five do), so a per-batch download is not a
per-cell partition — see the next section.

---

## Known limitations

**No wall-clock time, at all.** `t` resets to exactly 0.0 at the start of every one of
the 114,738 cycles, and no struct carries a date. Rests and gaps *between* cycles are
unrecoverable. No release can fix this.

**Physically impossible values exist and are flagged, not removed.** The 48 cycles
above. Nothing is clipped, winsorised or repaired.

**No C/10 cycle exists in any struct.** Measured over all 114,692 measured cycles: the
minimum peak |I| is **4.0006 C**, and no cycle anywhere has a peak below 1.0 C. The
dataset documentation describes C/10 reference cycles; they are not in these three
batches. (2018-02-20 carries four `SLOWCYCLE` policies, so they exist in the programme —
just not here.)

**Only the 2017-06-30 batch has observed crossings below 0.88 Ah.** It was cycled to
about 0.825 Ah; the other two stop at the criterion. That batch is also the one **public
mirrors most often omit** — a Kaggle copy with two batches is not the same dataset, and
any cross-batch claim made without it is made on two thirds of the data.

**The batches are not exchangeable.** Different CV cutoffs (C/50 vs C/20), different
rests, a ~1.4 C baseline offset in 2018-04-12, and a `Qdlin` capacity bias that varies
−27 to −49 mAh by batch. Keep `batch_date` as a factor; use `cv_splits("batch")` for any
generalisation claim. Pooled correlations flatter: ρ = −0.925 pooled against −0.785
within the weakest batch.

**`batch_date` is the *first* segment's, on every row.** Five cells were continued
across batches, and for them `batch_date` names the wrong file: a segment-2 cycle of
`EL150800460514` says `2017-05-12` while its series sit in
`within_cycle_2017-06-30.h5`. **Use `source_batch_date`** — which is why
`load_cycle_features` returns that and not `batch_date`. The five are
`EL150800460486`, `EL150800460514`, `EL150800460623`, `EL150800464865`,
`EL150800464977`.

**Cells are never addressed by struct position.** No struct stores its rows in channel
order: `source_struct_index` differs from `source_channel - 1` for **113 of the 140**
struct rows. Join on `(cell_uid, cycle)`, never on row position, and resolve names like
"b1c18" through the decoded `channel_id` (that one is channel 17).

**`Qdlin` understates discharge capacity** by a median 31.9 mAh (~3%), because `Vdlin`
starts at 3.5 V, below the 3.6 V charge cutoff, so the top of the discharge curve is off
the grid. Per batch: −36.4 / −49.4 / −27.4 mAh. Do not read `Qdlin[-1]` as the cycle's
capacity.

**Only `QDischarge` is in the three v1.0 CSVs.** `IR`, `QCharge`, the temperatures and
`chargetime` arrive with v0.2.0; the nine series and the grid with v0.3.0.

**Other MATR batches are out of scope.** 2018-02-20 and 2018-04-03 are readable and
share **no barcode** with these 135 cells; the 2019-01-24 file on data.matr.io is a
**truncated download** (h5py reports 572 MB against a stored EOF of 2.60 GB) and cannot
be opened at all.

---

## What this does not include

**One measurement per cycle.** Of everything the source structs record per cycle, the
three CSVs carry exactly **one measured quantity: `QDischarge`**, as `QD_Ah` — plus
`cycle` (the index), `soh` (`QD_Ah` / 1.1) and `cycles_to_eol`, both derived from it, and
the quality flags. `analysis_set_cycles.csv` is 113,559 rows × 13 columns:

```
cell_uid  batch_date  channel  cycle  segment  QD_Ah  soh  cycles_to_eol
is_measured_cycle  is_artifact_cycle  is_restart_cycle  is_junction_cycle  is_clean_cycle
```

**These struct fields are *not* in any of the three CSVs:**

| | field | what it is | arrives |
|---|---|---|---|
| summary, per cycle | `IR` | internal resistance, Ω | **v0.2.0** |
| | `QCharge` | charge capacity, Ah | **v0.2.0** |
| | `Tavg`, `Tmax`, `Tmin` | cell temperature, °C | **v0.2.0** |
| | `chargetime` | minutes to charge | **v0.2.0** |
| within-cycle series | `t`, `I`, `V` | time, current (as a C-rate), voltage | v0.3.0 |
| | `Qc`, `Qd` | charge / discharge throughput, Ah | v0.3.0 |
| | `T` | temperature trace, °C | v0.3.0 |
| | `Qdlin`, `Tdlin`, `discharge_dQdV` | the three 1000-point voltage-grid series | v0.3.0 |
| the grid itself | `Vdlin` | 1000 points, 3.5 → 2.0 V, identical for every cell | v0.3.0 |

The six marked **v0.2.0** are available now, from `load_cycle_features()` — they are
columns of the v1.1 per-cycle index, which is a CSV. Everything marked v0.3.0 is
HDF5-only. `mc.describe()` prints this list with the counts computed live.

So the ΔQ(V) curves the original paper is built on cannot be computed from the three
CSVs alone, and nor can anything needing a within-cycle trace. Temperature, resistance
and charge time no longer belong on that list: `load_cycle_features()` returns them.
`chargetime` is worth naming — it was *used* to derive `is_restart_cycle`, and as of
v0.2.0 the column itself is carried too.

**v0.3.0 reads the rest.** The within-cycle extraction adds the nine series and the
voltage grid as three HDF5 files, behind an optional extra:
`pip install "matr-clean[series]"`. The files themselves are published (DOI
`10.5281/zenodo.23984188`) and the loader can already download them; what is not here
yet is the code that reads them, so until that lands the raw `.mat` files remain the
only route to the series.

**The raw `.mat` files are not used and not needed.** This loader never opens them, and
v0.2.0 requires no `h5py` at all. If you do need voltage-domain features before that release,
that is a separate job against the raw files — `exploration/matr.py` in this repository
reads them lazily — and it starts by downloading ~8 GB from [data.matr.io](https://data.matr.io/1/projects/5c48dd2bc625d700019f3204).

**Nothing is masked, imputed, interpolated or smoothed.** Bad cycles are flagged in
place so each reason stays visible: `is_measured_cycle`, `is_artifact_cycle`,
`is_restart_cycle`, `is_junction_cycle`, and `is_clean_cycle` as the conjunction of all
four. `clean=True` filters on the conjunction; `clean=False` returns every row with the
flags intact.

**`is_clean_cycle` is a summary-level flag, and only that.** All four flags it combines
are judgements about a cycle's **`QDischarge` value and its neighbours** —
`is_artifact_cycle` is a departure from an 11-cycle rolling median, `is_restart_cycle`
reads `chargetime`, `is_junction_cycle` is proximity to a continuation seam. None of them
looks inside a cycle. So `is_clean_cycle == True` says the cycle's *capacity* is sound; it
is **not** a warrant that the cycle's voltage, current, temperature or time series are
usable, and it must not be used as one in voltage-domain or time-series work. A cycle can
be clean here and still carry a broken trace. Use `is_series_valid` for that question —
`require_series_valid=True` on `load_cycles`, or `load_cycle_features`, which applies it
by default. It is computed from each cycle's own series with no rolling window, it fails
on 249 cycles across 97 cells, and `is_clean_cycle` is not a substitute for it. See
"Two quality flags, two different questions" above.

**The batches are not exchangeable.** Target medians are 841 / 481 / 1004 cycles, partly
by design and partly protocol (`REPORT.md` §8). Keep `batch_date` in any model, and do
not split cells randomly across batches — `cv_splits` never does.

---

## Licensing

**The data is CC BY 4.0.** `analysis_set_cells.csv`, `analysis_set_cycles.csv` and
`cell_inventory.csv` are adaptations of the Toyota Research Institute dataset and are
redistributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The
attribution text to use, verbatim, is in [`NOTICE.md`](NOTICE.md) and in `README.md`
under "Licensing". If you publish anything built on this, cite Severson et al. (2019)
and the dataset.

**The code is MIT** — this package and everything under `exploration/`. See
[`LICENSE`](LICENSE); [`NOTICE.md`](NOTICE.md) records which terms cover which files.
