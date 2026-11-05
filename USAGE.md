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
!pip install -q "git+https://github.com/tayebelleuch-ops/deep-analysis-of-MIT-TOYOTA-dataset.git@loader-v0.1.0"
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

> `loader-v0.1.0` is the tag for this loader release. Use the **loader** tag here, not
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

| | field | what it is |
|---|---|---|
| summary, per cycle | `IR` | internal resistance, Ω |
| | `QCharge` | charge capacity, Ah |
| | `Tavg`, `Tmax`, `Tmin` | cell temperature, °C |
| | `chargetime` | minutes to charge |
| within-cycle series | `t`, `I`, `V` | time, current (as a C-rate), voltage |
| | `Qc`, `Qd` | charge / discharge throughput, Ah |
| | `T` | temperature trace, °C |
| | `Qdlin`, `Tdlin`, `discharge_dQdV` | the three 1000-point voltage-grid series |
| the grid itself | `Vdlin` | 1000 points, 3.5 → 2.0 V, identical for every cell |

So the ΔQ(V) curves the original paper is built on cannot be computed from this loader,
and neither can anything needing temperature, resistance, charge time or a within-cycle
trace. `chargetime` is a case worth naming: it was *used* to derive `is_restart_cycle`,
but the column itself is not carried.

**A later release will read them.** A within-cycle extraction keyed to this same analysis
set is in progress, and will add the six summary series, the nine within-cycle series and
the voltage grid. It is **not released**: nothing in this package reads them yet, and
until it ships the raw `.mat` files are the only source.

**The raw `.mat` files are not used and not needed.** This loader never opens them, and
nothing here requires `h5py`. If you do need voltage-domain features before that release,
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
be clean here and still carry a broken trace. The v1.1 extraction adds a separate
`is_series_valid` for exactly that question, computed from each cycle's own series with no
rolling window — it is not released yet, and `is_clean_cycle` is not a substitute for it.

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
