# Stage 0 — inventory and extraction plan

**Status: proposed. Nothing has been extracted, written or uploaded.** The three raw
`.mat` files were opened `mode="r"` only; their sizes and mtimes are recorded in §9 and
re-checked at the end of every stage.

This document inventories what the v1.0 analysis set does **not** carry, measures how
large it is, and proposes a format, a layout and a hosting route. It changes no decision
(D0–D5), edits no existing document, and leaves `analysis_set_cells.csv`,
`analysis_set_cycles.csv`, `cell_inventory.csv` and the `v1.0` tag untouched.

Everything numeric below was read from the files by `probe_within_cycle.py` and
`probe_other_matr_files.py` (both new, both read-only). Where a figure contradicts
`schema.md` or `REPORT.md`, the contradiction is stated in §10 rather than resolved
silently.

---

## 1. What the analysis set carries, and what it therefore omits

`analysis_set_cycles.csv` is **113,559 rows × 13 columns**, one row per kept cycle:

```
cell_uid  batch_date  channel  cycle  segment  QD_Ah  soh  cycles_to_eol
is_measured_cycle  is_artifact_cycle  is_restart_cycle  is_junction_cycle  is_clean_cycle
```

Of the struct's own per-cycle content that is exactly **one** field — `QDischarge`,
carried as `QD_Ah` — plus `cycle`, `soh` (= `QD_Ah` / 1.1) and the derived flags.

The three structs hold **114,738 cycles** in total (46 + 48 + 46 rows: 38,811 + 24,920 +
51,007). The analysis set keeps 113,559 of them, so **1,179 cycles are absent entirely**
and for the 113,559 that are present, nine within-cycle series and six summary series
are absent. Reconciliation:

```
struct cycles                                   114,738
− truncated past the 0.88 Ah crossing (D2)       −1,179   all in 2017-06-30
                                                =113,559   = analysis_set_cycles.csv
```

The 1,179 figure matches `Σ analysis_set_cells.n_cycles_truncated` exactly, and all of it
falls in 2017-06-30, as D2 states.

> **One correction to the brief.** The 46 leading placeholder cycles are **not** excluded
> from the analysis set. They are present, carried with `is_measured_cycle = False` (and
> therefore `is_clean_cycle = False`). So the only cycles missing from v1.0 are the 1,179
> truncated ones. The extraction still needs an `is_placeholder` column, because the
> placeholder rows are *structurally* different in the raw files (see §2.1), but they do
> not need recovering — they were never dropped.

---

## 2. Complete field inventory, verified from the files

All three files carry an identical schema: top level `['#refs#', '#subsystem#', 'batch',
'batch_date']`, and `batch` with exactly eight fields (`Vdlin`, `barcode`, `channel_id`,
`cycle_life`, `cycles`, `policy`, `policy_readable`, `summary`). There are **no fields
beyond those documented in `schema.md`** — the list below is complete, not a selection.

### 2.1 The nine within-cycle series — none is in the analysis set

Dereferenced as `cycles[field][j, 0]`; every one is **float64**, stored `(1, n)`.

| field | unit | length | observed range (sampled, 420 cycles) |
|---|---|---|---|
| `t` | minutes since the start of the cycle | native | 0 … 552.08 |
| `I` | **C-rate**, not amperes | native | −4.009 … **+8.013** |
| `V` | V | native | 0 … 3.618 |
| `Qc` | Ah (charge throughput) | native | 0 … 1.0786 |
| `Qd` | Ah (discharge throughput) | native | 0 … 1.0787 |
| `T` | °C | native | 0 … 43.77 |
| `Qdlin` | Ah, interpolated onto `Vdlin` | 1000 | **−51.57 … +52.45** |
| `Tdlin` | °C, interpolated onto `Vdlin` | 1000 | 0 … 42.06 |
| `discharge_dQdV` | Ah/V, interpolated onto `Vdlin`; ≤ 0 | 1000 | −31.98 … 0 |

`I` in C-rate is confirmed: the discharge floor sits at −4.0 for a 4C policy on a 1.1 Ah
cell. The two bold ranges are not physical and are taken up in §9 and §10.

**The six native-length fields always share one length.** Verified on every cycle of all
140 rows: `len(Qc) == len(Qd) == len(T) == len(V) == len(t) == len(I)`, with no
exceptions. One length per cycle therefore indexes all six.

**The three grid fields are 1000 points except on the 46 placeholder cycles**, where they
are 2 points of zeros, like the native fields. So "1000" is a rule with exactly 46
documented exceptions — which is why the layout in §5 needs an explicit length column
rather than an assumed constant.

### 2.2 The voltage grid `Vdlin` — not in the analysis set, and not per cell

Read for **all 140 struct rows** (`schema.md` checked only the first and last of each
batch) and the result is stronger than documented: the grid is **byte-identical for every
cell of every batch**, 1000 points, 3.500 → 2.000 V, monotonically decreasing, uniform
step −0.00150150150…, float64.

It is **not** bitwise equal to `np.linspace(3.5, 2.0, 1000)`: 15 of the 1000 points differ,
by at most **4.44e-16** (1.3e-16 relative) — one ulp, i.e. MATLAB's and numpy's `linspace`
round differently in the last bit. `np.linspace(3.5, 2.0, 1000)` is therefore a correct
description to within a rounding bit but not a byte-exact substitute. The extraction will
store the grid **as read from the file**, once, so no reconstruction is needed.

The grid confirms `schema.md` against the brief: it runs from **3.5 V**, not 3.6 V. Since
the charge cutoff is 3.6 V, `Qdlin` does not cover the top 0.1 V of the discharge curve.

### 2.3 Summary fields absent from the analysis set — six of the eight

| field | unit | n values | NaNs | observed range |
|---|---|---|---|---|
| `IR` | Ω | 114,738 | 0 | 0 … 0.024405 |
| `QCharge` | Ah | 114,738 | 0 | 0 … **2.9659** |
| `Tavg` | °C | 114,738 | 0 | 0 … 41.44 |
| `Tmax` | °C | 114,738 | 0 | 0 … 44.66 |
| `Tmin` | °C | 114,738 | 0 | 0 … 36.69 |
| `chargetime` | minutes | 114,738 | 0 | 0 … 1290.37 |

The other two are `cycle` and `QDischarge`, both already carried. **No NaN in any summary
field anywhere**, confirming `REPORT.md` §4.4 at full coverage. `QCharge` reaching 2.97 Ah
on a 1.1 Ah cell is the restart artifact (two charges recorded in one row), and the
`chargetime` ceiling of 1290 min is the restart detector `REPORT.md` §4.1 uses.

These six are cheap — 6 × 114,738 float64 = 5.5 MB — and should simply be columns of the
per-cycle index table (§5), not a separate file.

### 2.4 Per-cell metadata absent from the cells table

| item | where it is now | note |
|---|---|---|
| `policy` (underscore form) | **nowhere** | e.g. `3_6C-80PER_3_6C`, `5C_67PER_4C_NEWSTRUCTURE`. `analysis_set_cells.policy_as_stored` keeps the *readable* form only |
| `cycle_life` (struct field) | `cell_inventory.csv:cycle_life_struct_field` | absent from `analysis_set_cells.csv`; 140 values, 2 NaN, range 148 … 1935 |
| `Vdlin` | nowhere | §2.2; one shared grid |
| struct row index | **nowhere** | needed as provenance: it is the only way a reader can re-verify that a cell was resolved by `channel_id`/barcode and not by position |
| `n_cycles` per struct row | `cell_inventory.csv:n_cycles_per_segment` | present |

Carrying the struct row index matters precisely *because* position must never be used to
address a cell. Recording the resolved position makes the resolution auditable instead of
implicit: for `EL150800453240` it records channel 17 at struct index 18, which is the
mismatch `schema.md` warns about.

---

## 3. The other MATR files in this repo — inventory only, not extracted

| file | bytes | rows | cycles | batch_date field | barcodes shared with the 135 |
|---|---|---|---|---|---|
| `Data/2019-01-24_…mat` | 572,094,998 | — | — | — | — |
| `dataset batteries/2018-02-20_…mat` | 2,022,599,329 | 47 | 26,904 | `2018-02-20` | **0** |
| `dataset batteries/2018-04-03_varcharge_…mat` | 89,125,795 | 2 | 1,053 | `2018-04-03_varcharge` | **0** |

`dataset batteries/` also holds byte-identical copies of the 2017-05-12 and 2018-04-12
published files.

**`2019-01-24` is an incomplete download, not another schema.** h5py cannot open it:
`eof = 572,094,486` against `stored_eof = 2,601,295,745`. The file on disk is 22% of the
file its own HDF5 superblock describes. `CLAUDE.md` calls it "an unconverted 2019-01-24
file" and `MANIFEST.md` calls it another MATR batch; neither records that it is truncated
and unreadable. Nothing in `exploration/` reads it, so nothing is affected.

Both readable files carry **exactly the same schema** as the published three — same eight
`batch` fields, same eight `summary` fields, same nine `cycles` fields — so the extraction
code would work on them unchanged. **They are out of scope and will not be extracted.**
Two observations from their metadata alone, both bearing on open questions in `REPORT.md`:

* **2018-02-20 is also missing channel 26** (47 rows: channels 1–25, 27–48). The published
  2018-04-12 is missing channels 26 **and** 31 (`REPORT.md` U1, open question 8). Channel
  26 being absent from two independent batches is consistent with a dead channel on the
  rig rather than two unrelated test failures. Observation only — two batches is not proof,
  and 2018-02-20 *has* a channel 31.
* **2018-02-20 carries four `SLOWCYCLE` policies** (`3.6C(80%)-3.6C(SLOWCYCLE`,
  `3.6C(9%)-5C(SLOWCYCLE`, `4.8C(80%)-4.8C(SLOWCYCLE`, `5.2C(58%)-4C(SLOWCYCLE`). The
  published three batches have no such policy string. This bears on `REPORT.md` open
  question 2 (where the C/10 cycles went) and is followed up, within the published
  batches only, at Stage 2 item 7.

---

## 4. Size census

Measured, not estimated: the length of all nine arrays of **every one of the 114,738
cycles** of all 140 struct rows was read from the files (`probe_within_cycle.py`, ~8 min).

### 4.1 Native array lengths

The six native fields share one length per cycle, verified on all 114,738 cycles with no
exceptions. Distribution of that length:

| batch | cycles | min | p25 | median | p75 | max | total points |
|---|---|---|---|---|---|---|---|
| 2017-05-12 | 38,811 | 2 | 1,037 | 1,065 | 1,085 | **31,104** | 40,951,666 |
| 2017-06-30 | 24,920 | 453 | 1,186 | 1,269 | 1,421 | **5,040** | 32,094,849 |
| 2018-04-12 | 51,007 | 648 | 706 | 730 | 754 | **61,901** | 38,822,223 |
| **all** | **114,738** | 2 | — | — | — | 61,901 | **111,868,738** |

The `min = 2` in 2017-05-12 is the 46 placeholders. The three grid fields take exactly
**two** distinct lengths across the whole dataset — 1000, and 2 on precisely those 46
placeholder rows (all 2017-05-12, all cycle 1), confirming `schema.md` exactly.

`schema.md` gives the native length as "~750–1100". The medians are 1,065 / 1,269 / 730, so
the typical value is right for two batches, but **2017-06-30's p75 is 1,421** and the
maxima reach 61,901 — see §10 item 3.

### 4.2 Totals and the cost of each precision

| | values | raw float64 | raw float32 |
|---|---|---|---|
| 6 native fields | 671,212,428 | 5.00 GiB | 2.50 GiB |
| 3 grid fields (×1000) | 344,214,000 | 2.56 GiB | 1.28 GiB |
| **total** | **1,015,426,428** | **7.57 GiB** | **3.78 GiB** |

### 4.3 Compression, measured

Trial on a 720-cycle sample (727,420 native points, spread over 10 cells per batch and 20
points through each cell's life), written through h5py with the byte-shuffle filter:

| configuration | bytes/value | fraction of raw float64 |
|---|---|---|
| float32, gzip-1, shuffle | 1.899 | 0.237 |
| **float32, gzip-4, shuffle** | **1.849** | **0.231** |
| float32, gzip-9, shuffle | 1.814 | 0.227 |
| float32, gzip-4, no shuffle | 2.462 | 0.308 |
| float64, gzip-4, shuffle | 4.853 | 0.607 |

gzip-9 buys 1.9% over gzip-4 for several times the CPU; the shuffle filter is worth 25%
and is free. **float32 + gzip-4 + shuffle** is the recommendation.

### 4.4 Projected output sizes

At the measured 1.849 bytes/value:

| file | cycles | values | compressed |
|---|---|---|---|
| `within_cycle_2017-05-12.h5` | 38,811 | 362,142,996 | **0.67 GB** |
| `within_cycle_2017-06-30.h5` | 24,920 | 267,329,094 | **0.49 GB** |
| `within_cycle_2018-04-12.h5` | 51,007 | 385,954,338 | **0.71 GB** |
| `within_cycle_index.csv` | 114,738 | 20 columns | ~14 MB |
| **total** | **114,738** | **1,015,426,428** | **≈1.88 GB** (1.75 GiB) |

Every HDF5 file is comfortably under the **2 GiB** GitHub release-asset limit, with the
largest at 36% of it, so no splitting or multi-part archive is needed.

### 4.5 float32 is lossless enough — measured against the checks it has to survive

Round-trip float64 → float32 → float64 over 900 cycles (5 points through each of the 140
rows' lives, 703,774 native and 654,092 grid points per field):

| field | max absolute error | max relative error | in physical terms |
|---|---|---|---|
| `V` | 5.0e-08 V | 2.5e-08 | 50 nV, against a 3.6 V span |
| `Qc`, `Qd` | 5.0e-08 Ah | 5.0e-08 | 0.05 µAh, against the **0.2 mAh** integration resolution `REPORT.md` §4.4 identifies — **4,000× smaller** |
| `I` | 4.8e-07 C | 6.0e-08 | 0.5 µC on a ±8 C span |
| `T`, `Tdlin` | 1.9e-06 °C | 6.0e-08 | against thermocouple residuals quoted to 0.01 °C |
| `Qdlin` | 1.9e-06 Ah | 6.0e-08 | against the **0.01 Ah** `is_artifact_cycle` cutoff — 5,000× smaller |
| `discharge_dQdV` | 8.4e-07 Ah/V | 5.9e-08 | on a ±32 Ah/V span |
| `t` | 3.1e-05 min | 6.0e-08 | **1.8 ms**, against a ~5 s sampling interval |

No field exceeds 6.0e-08 relative error, which is simply float32's half-eps — the
conversion is as good as float32 can be. Every physical tolerance any Stage 2 check uses
is three to five orders of magnitude coarser. `t` is the only field where a *difference*
rather than a value matters (the non-monotonic-time check): consecutive differences carry
up to 3.6 ms of error against a ~5 s interval, i.e. 0.07%, and no genuine sample spacing is
anywhere near that small.

**float32 is nonetheless not bit-exact** — only 0.01–16% of values survive the round trip
unchanged — so the proposal is explicit: the published arrays are float32, and **every
Stage 2 residual is computed from the float64 source during extraction**, so no audit
number depends on the conversion. Stage 3 then re-runs the Stage 2 checks against the
published float32 files and reports whether any verdict moves. If the decision is
float64 instead, the total goes to ~4.9 GB and 2018-04-12 alone exceeds the 2 GiB
per-asset limit, forcing a split.

---

## 5. Proposed format and layout

**HDF5 for the arrays, one file per batch, plus one CSV index for the whole extract.**

### 5.1 Why HDF5 rather than Parquet

* **No new dependency.** `h5py` 3.16.0 is already in the pinned environment and is what
  `matr.py` reads with. **`pyarrow` is not installed**, and pandas 3.0.6 cannot write
  Parquet without it — choosing Parquet means adding a dependency to `requirements.txt`,
  which is an existing file this work is not supposed to edit.
* **The data is ragged.** Native lengths run 2 … 61,901. In HDF5 that is one concatenated
  1-D dataset per field plus an offsets vector — a CSR layout, exact and compact. In
  Parquet it is a `list<float>` column, which costs more per row and gives worse random
  access.
* **The grid fields are naturally a matrix.** `(n_cycles, 1000)` chunked `(64, 1000)` is
  exactly the shape ΔQ(V) work wants, and one cycle, or 64, can be read without touching
  the rest of the file.
* **Random access without a full read** matters here: at 1.88 GB nobody should have to
  load a whole batch to look at one cell.

Parquet's advantages — ecosystem, predicate pushdown — apply to the *index*, which is
small, tabular and shipped as CSV for exactly the reasons the v1.0 files are CSV:
diffable, hash-stable, readable without any library.

### 5.2 Layout of each `within_cycle_<batch_date>.h5`

```
/vdlin                         float64 (1000,)      the grid as read from the file, not reconstructed
/native/offset                 int64   (n_cycles+1,) CSR offsets; cycle r is [offset[r]:offset[r+1]]
/native/I                      float32 (N_pts,)     C-rate
/native/V                      float32 (N_pts,)     V
/native/T                      float32 (N_pts,)     degC
/native/Qc                     float32 (N_pts,)     Ah
/native/Qd                     float32 (N_pts,)     Ah
/native/t                      float32 (N_pts,)     minutes from the start of the cycle
/grid/Qdlin                    float32 (n_cycles, 1000)   Ah       on /vdlin
/grid/Tdlin                    float32 (n_cycles, 1000)   degC     on /vdlin
/grid/discharge_dQdV           float32 (n_cycles, 1000)   Ah/V     on /vdlin, <= 0
/row/cell_uid                  bytes   (n_cycles,)  the key, redundant with the index for self-containment
/row/cycle                     int32   (n_cycles,)
```

Chunking `(65536,)` for the native 1-D datasets and `(64, 1000)` for the grid matrices;
gzip level 4 with the shuffle filter on every dataset. Units are written as an HDF5
attribute on each dataset, so the file documents itself.

The **46 placeholder rows get NaN** in the three grid matrices, because a fixed-width
matrix cannot hold a length-2 row. Nothing is lost: the placeholder's actual content is
two zeros in every one of the nine fields — stated here, recorded per row as
`grid_len_raw = 2`, and **preserved exactly in the native CSR arrays**, which are ragged
and so store the two zeros verbatim. NaN is chosen over 0.0 so that a reader who ignores
the flags gets an obviously missing value rather than a plausible one.

### 5.3 `within_cycle_index.csv` — 114,738 rows, one per struct cycle

| column | type | meaning |
|---|---|---|
| `cell_uid` | str | upper-cased barcode; joins to both v1.0 analysis-set files |
| `cycle` | int | **the analysis set's numbering** (§7), 1-based, continuous across segments |
| `segment` | int | 1-based segment index |
| `source_batch_date` | str | the batch the row's data actually came from |
| `source_channel` | int | resolved from `channel_id`, never from position |
| `source_struct_index` | int | provenance: where that resolution landed |
| `source_cycle_index` | int | 0-based index into that row's `cycles` group |
| `h5_row` | int | row position in that batch's HDF5 datasets |
| `n_samples` | int | native length; `offset[r+1] − offset[r]` |
| `grid_len_raw` | int | 1000, or 2 on the 46 placeholders |
| `in_analysis_set` | bool | §6 |
| `beyond_crossing` | bool | §6 |
| `is_placeholder` | bool | §6 |
| `QDischarge_Ah` | float | carried as the join proof (§7 check 3) |
| `IR_ohm` | float | summary field absent from v1.0 |
| `QCharge_Ah` | float | " |
| `Tavg_C`, `Tmax_C`, `Tmin_C` | float | " |
| `chargetime_min` | float | " |

The index is **~14 MB and small enough to commit to the repository**, so a teammate gets
the per-cycle summary fields, the flags and the full join without downloading anything.
Only the 1.88 GB of arrays is hosted externally. That roughly doubles the repository's
11 MB; if that is unwanted the alternative is `gzip -n` (≈3 MB, still deterministic), and
the decision is listed in §13.

A second small table, `within_cycle_cells.csv` (135 rows), carries the per-cell items §2.4
lists as absent: the underscore `policy` string, the struct's own `cycle_life` field, and
the resolved `(batch_date, channel, struct_index)` per segment.

## 6. Proposed treatment of the cycles the analysis set excludes

Nothing is dropped. Every one of the **114,738** struct cycles gets a row, and the rows
the analysis set does not contain are marked by flag, so the join is explicit and
auditable in both directions.

| column | meaning | n rows |
|---|---|---|
| `in_analysis_set` | the row is one of the 113,559 rows of `analysis_set_cycles.csv` | 113,559 |
| `beyond_crossing` | truncated by D2: past the cell's 0.88 Ah crossing | 1,179 |
| `is_placeholder` | 2017-05-12's zero-filled cycle 1; all nine series are 2 zeros | 46 |

`in_analysis_set` is exactly `~beyond_crossing`, and `is_placeholder` rows are a subset of
`in_analysis_set` (see the correction in §1). The three are kept as separate columns
anyway, because `is_placeholder` is a statement about the *file* and `beyond_crossing` a
statement about **D2**, and conflating them is how the "placeholders were dropped" reading
arises in the first place.

The flags carried by `analysis_set_cycles.csv` — `is_measured_cycle`,
`is_artifact_cycle`, `is_restart_cycle`, `is_junction_cycle`, `is_clean_cycle` — are
**not** copied. They stay in the v1.0 file as the single source of truth, reached by a
join on `(cell_uid, cycle)`. Copying them would create a second place for them to drift.

## 7. Keys, and how the new data joins to the analysis set

The key is **`(cell_uid, cycle)`**, in exactly the numbering `analysis_set_cycles.csv`
uses. That numbering is not the struct's own, so it is restated here precisely, from
`build_analysis_set.py`:

* `cell_uid` is the **upper-cased barcode**. Barcode case is inconsistent between files
  (`schema.md`), so the join must upper-case first.
* A cell's segments are concatenated in the order given by
  `analysis_set_cells.all_segments` (e.g. `2017-05-12:ch1 | 2017-06-30:ch1`).
* `cycle` = that segment's own `summary["cycle"]` **plus the total cycle count of all
  preceding segments**. Since each segment's `cycle` runs 1…n contiguously, the joined
  numbering runs 1…Σn contiguously. For the 130 single-segment cells the offset is 0 and
  `cycle` is the struct's own cycle number.
* `segment` is 1-based. **`batch_date` and `channel` in the cycles table are the *first*
  segment's**, for every row — so a segment-2 row of a continuation cell carries
  `2017-05-12` even though its data came from the 2017-06-30 file. Resolving a row back to
  a raw array therefore requires `segment`, not `batch_date`.

Inverting that to locate the raw source of row `(cell_uid, cycle)`:

```
offset = 0
for k, (date, ch) in enumerate(all_segments, start=1):
    n = n_cycles(date, ch)
    if cycle <= offset + n:
        struct_index = index_of_channel(date, ch)   # resolved via channel_id, never position
        cycle_index  = int(cycle - offset) - 1      # 0-based into the `cycles` group
        break
    offset += n
```

Every extracted row will carry `source_batch_date`, `source_channel`,
`source_struct_index` and `source_cycle_index` so this inversion is recorded in the data
rather than left to be re-derived. `source_struct_index` is provenance only: cells are
resolved by `channel_id` and barcode, and `source_struct_index` records where that
resolution landed so a reader can check it (it differs from `channel − 1` for 113 of the
140 rows).

**The join check, asserted at the end of extraction:**

1. every `(cell_uid, cycle)` in `analysis_set_cycles.csv` appears **exactly once** in the
   new index — 113,559 matches, no duplicates, no misses;
2. the rows in the new index that are *not* in `analysis_set_cycles.csv` are **exactly**
   the 1,179 with `beyond_crossing = True`;
3. `QDischarge` read fresh from the struct equals `analysis_set_cycles.QD_Ah` bit-for-bit
   on all 113,559 shared rows — which proves the numbering is aligned, not merely
   countable;
4. the 46 `is_placeholder` rows are exactly the rows with `is_measured_cycle = False`.

## 8. Memory and determinism

* **One cell at a time**, through `matr.BatchCycles`, which is already the lazy reader the
  audit uses. One cell's nine series peak at ~2,300 cycles × ~1,100 points × 9 × 8 B ≈
  180 MB, and that is the pathological longest cell; the median cell is under 70 MB.
  Nothing holds two cells at once and no pickle is touched.
* **Incremental writes.** Each cell's arrays are appended to resizable HDF5 datasets and
  flushed before the next cell is read, so peak RSS is one cell plus the HDF5 chunk cache.
  Target peak well under 1 GB on the 19 GB machine.
* **Determinism.** Cells are written in a fixed order — batch date ascending, then
  **channel** ascending (not struct position), then segment — and cycles in ascending
  `cycle`. No timestamps, no hostname, no library version and no run counter is written
  into any output. HDF5 is asked for a fixed chunk layout and a fixed gzip level, and the
  index tables are CSV written with an explicit column order and float format.
* **Byte-reproducibility will be demonstrated, not assumed**: Stage 3 deletes every output
  and re-runs, then compares SHA-256. HDF5 files can embed a creation-order timestamp in
  the superblock; if the first re-run is not byte-identical the extraction will set
  `libver` and `track_order` explicitly, or fall back to a documented
  "hash the dataset contents, not the container" rule — stated either way rather than
  quietly relaxed.

## 9. Raw inputs are read-only

Recorded at the start of Stage 0 and re-checked at the end of every stage:

| file | bytes | mtime (epoch) |
|---|---|---|
| `2017-05-12_batchdata_updated_struct_errorcorrect.mat` | 3,025,320,241 | 1792510152 |
| `2017-06-30_batchdata_updated_struct_errorcorrect.mat` | 2,007,331,155 | 1792509485 |
| `2018-04-12_batchdata_updated_struct_errorcorrect.mat` | 3,236,690,412 | 1792510707 |

Sizes match `MANIFEST.md` exactly. The files live outside this repository and are reached
through symlinks in `Data/`, which `.gitignore` excludes by content (`Data/*`), so neither
the symlinks nor the data can be committed. No copy of any raw file is made.

## 10. Disagreements with the documentation, found at Stage 0

Reported, not resolved. Proposed corrections go in `REPORT_v1.1.md` at Stage 3; no
existing document is edited.

| # | document | says | the files say |
|---|---|---|---|
| 1 | the brief | the interpolated curves are on a 3.6 V → 2.0 V grid | **3.5 V → 2.0 V**, 1000 points, verified on all 140 rows. `schema.md` is right |
| 2 | `schema.md` §`cycles` | `I` ranges "≈ −4.0 … +5.0" | max observed **+8.013 C** (2017-05-12). The floor, −4.009, is right |
| 3 | `schema.md` §`cycles` | `t` native length "~750–1100" | see §4: the range is far wider, and 2017-06-30 routinely exceeds 1100 |
| 4 | `schema.md` §`Vdlin` | the grid is `np.linspace(3.5, 2.0, 1000)` | true to 1 ulp, **not** bitwise: 15 of 1000 points differ by ≤4.44e-16 |
| 5 | `REPORT.md` §7 | `analysis_set_cycles.csv` … **12 columns**; `analysis_set_cells.csv` … **29 columns** | **13** and **31**. `cell_inventory.csv`'s stated 41 is correct |
| 6 | `MANIFEST.md`, `CLAUDE.md` | `Data/2019-01-24_…mat` is another MATR batch | it is a **truncated download**, 22% present, and h5py cannot open it |
| 7 | the brief | the leading placeholder cycles are excluded from the analysis set | they are **present**, flagged `is_measured_cycle = False`; only the 1,179 truncated cycles are absent |

## 11. Preview of what the within-cycle data already shows

Not findings yet — each is from a targeted probe, and each will be run over the full
extract at Stage 2 with its threshold and window stated. They are listed now because two
of them bear on whether the extraction is worth doing.

* **The restart cycles destroy `Qdlin`, by a factor the summary cannot show.** Scanning
  cycles 240–274 of all 48 cells of 2017-06-30 for `Qdlin` outside a generous
  [−0.05, 1.5] Ah band: **17 cycles across 14 channels**, with `Qdlin` reaching
  **−1186 … +1431 Ah** on channel 38 — about 1,300× nominal. The same cycles' *summary*
  artifact is −0.02 … −0.14 Ah, about 1%. Anyone computing ΔQ(V) without excluding
  restart cycles is mixing in values three orders of magnitude out of range.
* **At least one of those cycles is flagged clean in v1.0.** 2017-06-30 channel 8,
  cycle 248, carries `is_clean_cycle = True` and `Qdlin` spanning −50.3 … +87.7 Ah. Its
  capacity never departed far enough from the rolling median to trip the 0.01 Ah detector,
  so a summary-level detector could not have caught it. This is a gap in the v1.0 flags
  that only the within-cycle data reveals. (Channel 45 cycle 248 and channel 28 cycle 253
  *are* flagged; the rest are caught as artifacts.)
* **`EL150800453240` cycle 40 is a bad series, not a bad summary.** The brief asks which
  it is. The row holds **17,641 samples** against 1,658–2,198 for its neighbours, spans
  **2,729 minutes** (45 h), contains 10,505 discharge samples, and its own `Qd` ends at
  **2.8841 Ah** — the same value the summary reports. Integrating the discharge current
  gives **27.7 Ah**. So the summary faithfully reports a row that contains roughly 25
  discharges concatenated; the series is the corrupt thing. Cycles **39 and 41 of the same
  cell are also corrupt** and are flagged nowhere: both span >2,600 min, both contain a
  single ~42 h gap between consecutive samples, both have duplicated timestamps, and
  cycle 39 reaches **5.043 V** — impossible for this chemistry, which cuts off at 3.6 V.
  A normal cell at cycle 100 spans 44–60 min at a ~5.0 s interval with V inside
  [1.997, 3.600] and no duplicated timestamps.
* **Cycle-length bloat is confined to exactly two cells, and both are already notorious.**
  Counting cycles whose native length exceeds 5x their batch median: **2017-05-12 has 5,
  all on ch 17 (`EL150800453240`)** -- cycles 40 and 50-52, up to 31,104 samples against a
  1,065 median; **2018-04-12 has 48, all on ch 46 (`EL150800737364`)**, up to 61,901 against
  a 730 median; **2017-06-30 has none** (its longest, 5,040 on ch 12, is under 5x). ch 17 is
  `REPORT.md` U6 (the 2.884 Ah reading) and ch 46 is the cell the 2018-04-12 page calls
  noisy and the only cell carrying `exclude_from_deltaq_features`. So both summary-level
  diagnoses have a structural cause visible only in the series -- tens of thousands of
  samples per cycle -- and in ch 46's case it affects **48 cycles, not the 3 capacity
  artifacts** the v1.0 flags record.
* **The 1000-sample cap claim (`comparison_external_repos.md` §4.7) is confirmed in
  direction and overstated in magnitude.** That section probed 420 cycles and reported
  "59% of probed cycles lose data, averaging 9.4%". Over all 114,692 measured cycles:
  **50.4% are truncated, losing 6.55% of their samples on average** -- and the per-batch
  ordering it reports is exactly right (2017-06-30 worst at 92.6% of cycles / 21.1% of
  points, 2018-04-12 almost untouched at 1.2% / 0.14%). The gap is a sampling-weight
  artifact: probing three cycles per cell weights the 46 rows of 2018-04-12 equally with
  the rest, when that batch holds 44% of all cycles and is the one barely affected. Full
  by-age breakdown at Stage 2.

* **The sampling interval is not uniformly ~5 s.** `REPORT.md` §2 states ~5 s for all
  three batches and uses it to argue the IR pulse is ~1700× below resolution. Median
  intra-cycle intervals at cycle 100 include **2.11 s** (2017-06-30 ch 9) and **1.24 s**
  (ch 10) alongside the expected ~5.0 s. The conclusion about the IR pulse survives
  easily, but the stated interval does not hold batch-wide. Full census at Stage 2.

## 12. Hosting — the files must not go into git

The extract is ~1.9 GB compressed in total (§4), which rules out git: the repository is
currently 11 MB, `.gitignore` already excludes `*.h5`, and GitHub refuses single blobs
over 100 MB regardless. Two realistic routes.

### GitHub release assets

| | |
|---|---|
| limits | **2 GiB per file**, no documented total cap; release assets are not in the git history |
| pros | same account and repository, no second identity; `gh release upload` is scriptable, so the publish step is reproducible; downloads need no login; assets can be replaced without rewriting history |
| cons | **no DOI**, so the extract is not independently citable; assets are mutable and silently replaceable, so a hash recorded in a document is the only integrity guarantee; no long-term preservation commitment — if the repository is deleted the assets go with it; no landing page carrying the licence |
| fit | the per-batch files (§5) are each well under 2 GiB, so no splitting is needed |

### Zenodo

| | |
|---|---|
| limits | 50 GB per record by default, larger on request |
| pros | **DOI per version**, with a concept DOI that always resolves to the newest — which is what a teammate should cite; records are immutable once published, so a DOI pins exact bytes; explicit preservation commitment; the deposit form carries a licence field, so CC BY 4.0 is machine-readable; GitHub integration can mint a DOI per release |
| cons | a second account and a second place to keep in step; published records cannot be deleted or edited, only superseded — a mistake is permanent; upload is slower and the API is a further dependency; no access control, so publishing is irreversible |
| fit | the natural home if anyone outside the team is meant to cite this |

**Recommendation: both, with different jobs.** GitHub release assets on the `v1.1` tag for
day-to-day use by teammates, who already clone the repository; a Zenodo record of the same
bytes if and when the work is cited anywhere. SHA-256 of every file recorded in
`EXTRACTION.md` either way, which is what makes a mutable GitHub asset safe to rely on.

**Nothing will be uploaded without a separate explicit instruction.** Publishing to either
service is irreversible in practice (Zenodo strictly so), and the extract is an adaptation
of someone else's CC BY 4.0 data, so it is not a step to take on inference.

### Licence and attribution text each route needs

The extract is an **adaptation of CC BY 4.0 data** — the same status `NOTICE.md` assigns to
`analysis_set_*.csv` and `cell_inventory.csv` — so it must itself be offered under CC BY
4.0, with attribution and an indication of what was changed. The code that produces it
stays MIT under `LICENSE`. This follows the existing scope rule in `NOTICE.md`; it is not a
new licensing position.

Proposed text, to ship as a `LICENSE.txt` inside each release/record and to be quoted in
`EXTRACTION.md` (the citation block is `README.md`'s verbatim, with only the "Modified:"
sentence rewritten for this extract):

> These files are derived data, made available under Creative Commons Attribution 4.0
> International (CC BY 4.0) — https://creativecommons.org/licenses/by/4.0/
>
> Derived from Severson, K. A., Attia, P. M., Jin, N., Perkins, N., Jiang, B., Yang, Z.,
> Chen, M. H., Aykol, M., Herring, P. K., Fraggedakis, D., Bazant, M. Z., Harris, S. J.,
> Chueh, W. C., & Braatz, R. D. (2019). *Data-driven prediction of battery cycle life
> before capacity degradation.* Nature Energy, 4(5), 383–391.
> Dataset: https://data.matr.io/1/projects/5c48dd2bc625d700019f3204 (CC BY 4.0).
>
> Modified: the nine within-cycle series, the six uncarried summary series and the
> `Vdlin` voltage grid were extracted from the three raw `.mat` batch structs and
> rewritten as HDF5 plus a CSV index; cells were resolved by `channel_id` and barcode and
> keyed by upper-cased barcode; cycles of cells continued across batches were concatenated
> into one numbering; values were converted from float64 to float32; cycles excluded from
> the v1.0 analysis set are retained and flagged (`beyond_crossing`, `is_placeholder`)
> rather than dropped. No value was masked, imputed, smoothed or repaired. See
> `exploration/EXTRACTION.md` and `exploration/REPORT_v1.1.md`.

Route-specific additions:

* **GitHub release assets** — the attribution block above cannot live in release metadata
  in any machine-readable way, so it ships as `LICENSE.txt` beside the assets and is
  repeated in the release notes, which must also state that the assets are CC BY 4.0 and
  **not** covered by the repository's MIT `LICENSE`. Without that sentence a reader
  reasonably assumes the repository licence applies.
* **Zenodo** — set the record's licence field to `cc-by-4.0` (machine-readable), list the
  Severson et al. paper as a *related identifier* with relation **"isDerivedFrom"** against
  the dataset DOI, and put the "Modified:" paragraph in the description. Authors should be
  the repository's, not Severson et al.'s — the extract is our adaptation, and listing them
  as authors would imply endorsement that CC BY 4.0 explicitly forbids.

## 13. Decisions needed before Stage 1

1. **Format** — the §5 recommendation (HDF5 per batch + CSV index), or Parquet.
2. **Precision** — float32 for all nine series (recommended, §5), or float64 for `t`.
3. **Hosting** — GitHub release assets or Zenodo (§12).
4. **Tag name** for the new work, if it is to be tagged at all (`v1.1` is proposed).
5. **Whether `within_cycle_index.csv` (~14 MB) is committed** to the repository, or
   gzipped (~3 MB), or hosted with the arrays (§5.3).
