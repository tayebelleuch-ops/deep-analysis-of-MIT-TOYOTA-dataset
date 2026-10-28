# EXTRACTION — the within-cycle data, v1.1

What was extracted from the three raw MATR `.mat` batch structs that the v1.0 analysis
set does not carry, how it is stored, and how it joins back.

**This is additive.** No decision (D0–D5) changed, `analysis_set_cells.csv`,
`analysis_set_cycles.csv` and `cell_inventory.csv` are byte-identical to `v1.0`, and no
existing document was edited. The raw `.mat` files were opened `mode="r"` throughout and
their sizes and mtimes are re-checked by `extract_checks.py` on every run.

Findings from this data are in [`REPORT_v1.1.md`](REPORT_v1.1.md). Provenance and hashes
are in [`MANIFEST_v1.1.md`](MANIFEST_v1.1.md). The plan and the size census that led here
are in [`EXTRACTION_PLAN.md`](EXTRACTION_PLAN.md).

---

## 1. What is in the files

All nine within-cycle series, the `Vdlin` voltage grid, the six summary series v1.0 does
not carry, and the per-cell metadata absent from `analysis_set_cells.csv` — for **all
114,738 struct cycles**, including the 1,179 that D2 truncates and the 46 zero
placeholders. Nothing is dropped, masked, imputed, smoothed or repaired.

| file | rows | contents |
|---|---|---|
| `within_cycle_2017-05-12.h5` | 38,811 cycles | the nine series + the grid |
| `within_cycle_2017-06-30.h5` | 24,920 cycles | " |
| `within_cycle_2018-04-12.h5` | 51,007 cycles | " |
| `within_cycle_index.csv` | 114,738 | one row per cycle: keys, flags, summary fields, diagnostics |
| `within_cycle_cells.csv` | 135 | per-cell metadata absent from `analysis_set_cells.csv` |

## 2. HDF5 layout

```
/vdlin                       float64 (1000,)             V      the grid, as read from the struct
/native/offset               int64   (n_cycles+1,)       —      CSR offsets
/native/I                    float32 (N,)                C-rate
/native/V                    float32 (N,)                V
/native/T                    float32 (N,)                degC
/native/Qc                   float32 (N,)                Ah
/native/Qd                   float32 (N,)                Ah
/native/t                    float64 (N,)                minutes
/grid/Qdlin                  float32 (n_cycles, 1000)    Ah     on /vdlin
/grid/Tdlin                  float32 (n_cycles, 1000)    degC   on /vdlin
/grid/discharge_dQdV         float32 (n_cycles, 1000)    Ah/V   on /vdlin, <= 0
/row/cell_uid                bytes   (n_cycles,)
/row/cycle                   int32   (n_cycles,)
```

Each dataset carries its unit as an HDF5 attribute, so the file documents itself. Chunking
is `(65536,)` for the 1-D datasets and `(64, 1000)` for the grid matrices, gzip level 4
with the byte-shuffle filter.

**The six native series are ragged and share one length per cycle.** Verified on every
one of the 114,738 cycles without exception. Cycle at row `r` is
`native/<field>[offset[r] : offset[r+1]]`.

```python
import h5py, pandas as pd
idx = pd.read_csv("within_cycle_index.csv")
row = idx[(idx.cell_uid == "EL150800453240") & (idx.cycle == 40)].iloc[0]
with h5py.File(f"within_cycle_{row.source_batch_date}.h5", "r") as f:
    a, b = f["native/offset"][row.h5_row], f["native/offset"][row.h5_row + 1]
    V = f["native/V"][a:b]          # volts
    t = f["native/t"][a:b]          # minutes from the start of the cycle
    Qdlin = f["grid/Qdlin"][row.h5_row]      # Ah, on f["vdlin"][:]
```

### Precision

`t` is **float64**; the other eight series are **float32**. `t` is the only field whose
consecutive *differences* carry a verdict — the time-contiguity check — so it is kept
exact. float32 costs at most **6.0e-08 relative error** (float32's half-eps, measured over
900 cycles), which is three to five orders of magnitude below every physical tolerance any
check here uses: 0.05 µAh against the 0.2 mAh integration resolution, 1.9e-06 Ah against
the 0.01 Ah artifact cutoff, 50 nV on a 3.6 V span.

**Every diagnostic in the index was computed from the float64 source before narrowing**,
so no reported number depends on the conversion.

### `Vdlin`

1000 points, **3.500 → 2.000 V**, uniform step −0.00150150150…, monotonically decreasing,
**byte-identical for all 140 struct rows**. It is stored as read, not reconstructed: it is
not bitwise equal to `np.linspace(3.5, 2.0, 1000)` (15 of 1000 points differ, by ≤4.44e-16
— one ulp). Note it starts **below** the 3.6 V charge cutoff, so `Qdlin` misses the top of
the discharge curve; §2 of `REPORT_v1.1.md` measures how much.

### The 46 placeholder rows

2017-05-12's cycle 1 is a retained placeholder: all nine arrays are 2 zeros. The ragged
native datasets hold those two zeros **verbatim**. The fixed-width grid matrices cannot,
so those rows are **NaN**, `grid_len_raw = 2` records the true raw length, and
`is_placeholder` marks them. NaN rather than 0.0, so a reader who ignores the flags gets
an obviously missing value rather than a plausible one.

## 3. Keys, and the join to v1.0

The key is **`(cell_uid, cycle)`** in exactly the numbering of `analysis_set_cycles.csv`:

* `cell_uid` is the **upper-cased barcode**. Barcode case is inconsistent between files, so
  any join must upper-case first.
* Segments are concatenated in the order of `analysis_set_cells.all_segments`, and `cycle`
  is the segment's own `summary["cycle"]` plus the total cycle count of all preceding
  segments. For the 130 single-segment cells that is the struct's own cycle number.
* **`batch_date` and `channel` in `analysis_set_cycles.csv` are the *first* segment's, for
  every row.** A segment-2 row of a continuation cell carries `2017-05-12` there even
  though its data came from the 2017-06-30 file. This index therefore carries
  **`source_batch_date`** and **`source_channel`**, which say where the data actually is.

Cells are resolved through the decoded `channel_id` and barcode, **never by struct
position**. `source_struct_index` records the position each channel resolved to, as
provenance a reader can check — it differs from `channel − 1` for 113 of the 140 rows.

```python
cycles = pd.read_csv("analysis_set_cycles.csv")
merged = cycles.merge(idx, on=["cell_uid", "cycle"], how="left", validate="1:1")
```

### Join checks, asserted by `extract_checks.py` on every run

| check | result |
|---|---|
| index rows | 114,738 = every struct cycle |
| `(cell_uid, cycle)` unique | yes |
| every `analysis_set_cycles.csv` row appears exactly once | yes, 113,559 |
| rows **not** in the analysis set | exactly the 1,179 `beyond_crossing`, all 2017-06-30 |
| `QDischarge_Ah` vs `QD_Ah` on the 113,559 shared rows | **bit-for-bit identical** |
| `is_placeholder` vs `~is_measured_cycle` | identical; 46 rows, all 2017-05-12 cycle 1 |
| offsets, dataset lengths, grid shapes, row order, dtypes | consistent in all three files |
| 60 random cycles re-read from the raw `.mat` | round-trip exactly |
| v1.0 CSV SHA-256, raw `.mat` sizes and mtimes | unchanged |

The check count is **67 on a first run and 68 thereafter**: the first run *records*
the raw-file mtime baseline (`extract_out/raw_mtimes.txt`), every later run *compares*
against it, which is one extra assertion.

The `QDischarge_Ah` check is the one that matters: equal row *counts* would pass under a
misaligned numbering, bit-for-bit equality of the capacity value would not.

## 4. Columns of `within_cycle_index.csv`

**Keys and provenance:** `cell_uid`, `cycle`, `segment`, `source_batch_date`,
`source_channel`, `source_struct_index`, `source_cycle_index`, `h5_row`, `n_samples`,
`grid_len_raw`.

**Status flags:** `in_analysis_set`, `beyond_crossing`, `is_placeholder`,
`is_series_valid` plus its nine components (§5).

**Summary series v1.0 does not carry:** `IR_ohm`, `QCharge_Ah`, `Tavg_C`, `Tmax_C`,
`Tmin_C`, `chargetime_min`. `QDischarge_Ah` is carried too, as the join proof.

**Diagnostics**, all computed from the float64 source: `t_start_min`, `t_end_min`,
`dt_median_s`, `dt_min_s`, `dt_max_s`, `n_dt_nonpositive`, `n_dt_zero`, `V_min/max`,
`I_min/max`, `T_min/max`, `Qc_last`, `Qd_last`, `Qc_max`, `Qd_max`, `n_nan_native`,
`n_nan_grid`, `Q_dis_integral_Ah`, `Q_chg_integral_Ah`, `charge_time_min`, `cv_time_min`,
`cv_fraction`, `n_rest_samples`, `rest_longest_s`, `n_rest_runs`, `I_peak_abs`,
`programmed_rate_C`, `I_peak_over_programmed`, `Qdlin_min/max/last`, `Tdlin_min/max`,
`dQdV_min/max`, `dqdv_resid_rms`, `dqdv_resid_max`, `dqdv_num_absmax`,
`Tdlin_excess_over_T_max`, `Tdlin_shortfall_under_T_min`, `batch_median_n_samples`.

Carrying the diagnostics means any threshold here can be re-derived, or moved, without
re-reading 8 GB of raw data.

## 5. The series-validity flags

Nine checks, each answering one question about **one cycle's own series**. None uses a
rolling window over neighbouring cycles, which is what makes them independent of the v1.0
summary-level detectors (`is_artifact_cycle` is an 11-cycle rolling median on
`QDischarge`). `is_series_valid` is their conjunction, as `is_clean_cycle` is the
conjunction of the four v1.0 flags.

**Every cutoff sits in an observed gap in the measured distribution**, quoted below. Where
no gap separates signal from background the quantity is *reported and not flagged* — the
rule `REPORT.md` §4.3.1 sets for U2 and U12.

| flag | rule | cutoff, and the gap it sits in | n fail |
|---|---|---|---|
| `series_present` | `n_samples >= 10` | real cycles are 453+ samples; placeholders are 2 | 46 |
| `series_time_monotone` | `dt_min >= −1e-6 min` | worst step anywhere is −2.9e-11 s, i.e. float64 rounding; the tolerance is 9 orders above it and 4 below the 5 s sampling | **0** |
| `series_time_contiguous` | `dt_max <= 600 s` | ordinary steps top out at 5.1 s; the next largest is >1 h | 135 |
| `series_duration_plausible` | `t_end <= 240 min` | ordinary cycles end below 65 min; the next longest is >200 min | 131 |
| `series_length_plausible` | `n_samples <= 5 × batch median` | batch p25–p75 lies within ±5% of the median | 53 |
| `series_voltage_in_range` | `1.80 <= V <= 3.70` | highest ordinary `V_max` is 3.669 V, next is 4.462 V; lowest ordinary `V_min` is 1.889 V, next is 1.743 V | 15 |
| `series_current_in_range` | `peak \|I\| <= 1.50 × the cell's own programmed rate` | ratio is tight to ~1.12, then empty from 1.272 to 2.062 | 3 |
| `series_grid_in_range` | `Qdlin ∈ [−0.10, 1.50]` Ah, `Tdlin ∈ [0, 80]` °C, `dQdV ∈ [−200, 0]` | nominal is 1.1 Ah; failures reach ±4,030 Ah | 48 |
| `series_no_nan` | no NaN in any of the nine series | exact | **0** |
| **`is_series_valid`** | all nine | | **249** across 97 cells |

**Peak current is judged against the cell's own programmed rate, not an absolute ceiling.**
2017-05-12 contains 7C and 8C charging policies, so an absolute 7 C cutoff flags 8,600
cycles that are doing exactly what they were programmed to do. `programmed_rate_C` is
`max(policy_C1, policy_C2, 4.0)` — 4C because every policy discharges at ≥4C.

Two quantities are **reported, not flagged**, because no cutoff separates them from the
background: 418 cycles drawing 1.10–1.50× their programmed rate, and 35 measured cycles
containing one duplicated timestamp.

## 6. Reproduction

```bash
cd "$(git rev-parse --show-toplevel)"
ln -s /path/to/raw/2017-05-12_batchdata_updated_struct_errorcorrect.mat Data/   # and the other two
.venv/bin/python -I exploration/extract_within_cycle.py      # ~18 min, writes the HDF5 + raw index
.venv/bin/python -I exploration/extract_flags.py             # series-validity columns
.venv/bin/python -I exploration/extract_checks.py            # 67/68 checks + SHA256SUMS.txt
# Stage 2 analysis
.venv/bin/python -I exploration/v11_structure.py
.venv/bin/python -I exploration/v11_voltage_domain.py
.venv/bin/python -I exploration/v11_artifacts.py
```

Outputs land in `exploration/extract_out/`, which is **self-ignoring**: it contains a
`.gitignore` of `*` so no `.h5` or index CSV can be committed by accident. Peak memory is
one cell at a time, ~184 MiB at worst.

**Determinism.** Cells are written in ascending *channel* order (not struct order), cycles
in ascending cycle order, `track_times=False` on every dataset, and no timestamp, hostname
or version string is written into any output. Verified: deleting every output and
re-running reproduces all six files byte-for-byte.

## 7. SHA-256

See [`MANIFEST_v1.1.md`](MANIFEST_v1.1.md), which carries the hashes, sizes and the
environment, and is the provenance record for the proposed `v1.1` tag.

## 8. Licence

These files are **derived data** — an adaptation of CC BY 4.0 data — and carry the
dataset's terms, not this repository's MIT licence, exactly as `NOTICE.md` assigns for
`analysis_set_*.csv` and `cell_inventory.csv`. The code that produces them is MIT.

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
> into one numbering; eight of the nine series were converted from float64 to float32
> (`t` was not); cycles excluded from the v1.0 analysis set are retained and flagged
> (`beyond_crossing`, `is_placeholder`) rather than dropped; nine series-level validity
> flags were added. No value was masked, imputed, smoothed or repaired. See
> `exploration/EXTRACTION.md` and `exploration/REPORT_v1.1.md`.

This text ships as `LICENSE.txt` beside the data files. **Nothing has been uploaded.**
Hosting is to be a single canonical Zenodo record, preceded by a sandbox rehearsal, and
only after explicit confirmation; `MANIFEST_v1.1.md` §Hosting records what that needs.
