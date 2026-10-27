# Schema of the MATR batch structs, verified from the files

Everything below was read directly out of the three `.mat` files with `h5py`, not
taken from the README or from memory. Probe scripts: `probe_schema.py`,
`probe_strings.py`, `probe_subsystem.py`, `probe_mcos.py`, `probe_join.py`.
Accessor used by the rest of the exploration: `matr.py`.

Files read (opened `mode="r"` only):

| batch date | path | struct rows |
|---|---|---|
| 2017-05-12 | `Data/2017-05-12_batchdata_updated_struct_errorcorrect.mat` | 46 |
| 2017-06-30 | `Data/2017-06-30_batchdata_updated_struct_errorcorrect.mat` | 48 |
| 2018-04-12 | `Data/2018-04-12_batchdata_updated_struct_errorcorrect.mat` | 46 |

`Data/` also contains `2019-01-24_...mat`, and `dataset batteries/` contains
`2018-02-20_...mat` and `2018-04-03_varcharge_...mat`. **These are other batches of
the MATR programme and are not part of the 124-cell dataset described by the four
pages**, so nothing here touches them.

## Top level

```
/batch_date          char, e.g. "2017-05-12"   <- authoritative batch date
/batch               struct of 8 fields, each (n_cells, 1) object references
/#refs#              dereference target for everything in /batch
/#subsystem#/MCOS    MATLAB object store; holds barcode and channel_id strings
```

`batch` field names, all `(n_cells, 1)` arrays of HDF5 object references:

| field | MATLAB class | content |
|---|---|---|
| `barcode` | `string` | 14-char cell barcode, e.g. `EL150800460514` |
| `channel_id` | `string` | Arbin channel number as text, `"1"`..`"48"` |
| `policy` | `char` | underscore form, e.g. `3_6C-80PER_3_6C` |
| `policy_readable` | `char` | printable form, e.g. `3.6C(80%)-3.6C` |
| `cycle_life` | double | one number — **see the warning below** |
| `Vdlin` | double | (1, 1000) voltage interpolation grid |
| `summary` | struct | 8 per-cycle series |
| `cycles` | struct | 9 within-cycle series per cycle |

The number of cells is `batch["summary"].shape[0]`.

### String fields need two different decoders

`policy` and `policy_readable` are MATLAB `char`: UTF-16LE, decode with
`np.ravel(ds).astype(np.uint16).tobytes().decode("utf-16-le")`.

`barcode` and `channel_id` are MATLAB **`string` objects**, which is why upstream's
README says "barcode and channel are currently not available in the pkl files" and
why `build_pkl.py` omits them. They are present, just not where h5py can see them:
the dataset at the reference holds a six-element MCOS header

```
[0xdd000000, ndims=2, dim1=1, dim2=1, object_id, class_id]
```

and the payload lives in `/#subsystem#/MCOS`, a `(1, 95)` cell array whose element 0
is the class-metadata blob and whose **element `object_id + 1`** holds the object. That
element is a `uint64` vector laid out

```
[version, ndims, dim1, dim2, n_chars, <UTF-16 chars packed 4 per uint64>]
```

Implemented in `matr.decode_mcos_string`. Verified on 2017-05-12: object ids 1..46 are
the 14-character barcodes and ids 47..92 are the channel strings, with id 47 → `"1"`
and id 92 → `"48"`; and the decoded barcodes reproduce two values quoted on the pages,
`EL150800460623` for 2017-06-30 ch 3 and `el150800460605` for 2017-06-30 ch 10.

**Barcode case is inconsistent between files.** 2017-05-12 stores all 46 as `EL…`;
2017-06-30 stores 43 as `el…` and 5 as `EL…`; 2018-04-12 stores 45 as `el…` and 1 as
`EL…`. The 5 uppercase ones in 2017-06-30 are exactly the 5 cells carried over from
2017-05-12. Any join on barcode must upper-case first.

### Struct row order is not channel order

**None of the three batches stores its rows in channel order.** The first few rows of
each happen to be ascending, which makes the files look ordered, but every batch breaks:

| batch | first inversion | example |
|---|---|---|
| 2017-05-12 | struct index 6 | ch 10 followed by ch 9; index 18 is **channel 17**, not 21 |
| 2017-06-30 | struct index 6 | ch 15 followed by ch 1; index 1 is channel 10, index 7 is channel 1 |
| 2018-04-12 | struct index 9 | ch 19 followed by ch 1; index 20 is channel 2 |

Upstream addresses cells by struct index throughout (`b1c8`, `b2c7`,
`batch2_idx = [8:10,16:17]`, `nind = [3, 40:41]`), and those indices do **not** equal
channel numbers in any batch — `b2c7, b2c8, b2c9, b2c15, b2c16` are channels 1, 2, 3, 5
and 6, the same cells the page names, despite looking different. Likewise
`eda_utils.despike`'s "b1c18" is channel 17.

**Address cells by channel + barcode, never by struct index**, and never assume
`index + 1 == channel`.

## `summary` — one value per cycle

All eight are plain `(1, n_cycles)` float64 (not references). Units read off the
observed ranges:

| field | unit | note |
|---|---|---|
| `cycle` | — | 1-based cycle number, `1 … n_cycles`, contiguous |
| `QDischarge` | Ah | the capacity-fade signal; `QD` in the pkl files |
| `QCharge` | Ah | `QC` in the pkl files |
| `IR` | Ω | ~0.015–0.018 Ω |
| `Tavg`, `Tmin`, `Tmax` | °C | ~30–36 °C |
| `chargetime` | minutes | 0→80% SOC; median 10.04 in 2018-04-12 |

`len(summary["cycle"]) == n_cycles` in every cell of all three batches.

## `cycles` — within-cycle series

`(n_cycles, 1)` object references per field; dereference `cycles[field][j, 0]`.

| field | unit | length |
|---|---|---|
| `t` | minutes | native sample count (~750–1100) |
| `I` | C-rate (not A) | native; ranges ≈ −4.0 … +5.0 for a 4C discharge / 5C charge |
| `V` | V | native; spans the 2.0–3.6 V cutoffs exactly |
| `Qc`, `Qd` | Ah | native |
| `T` | °C | native |
| `Qdlin` | Ah | **1000**, interpolated onto `Vdlin` |
| `Tdlin` | °C | **1000**, interpolated onto `Vdlin` |
| `discharge_dQdV` | Ah/V | **1000**, interpolated onto `Vdlin`; ≤ 0 |

`I` is in C-rate, not amperes: a 4C discharge of a 1.1 Ah cell is 4.4 A, and the
observed minimum is −4.0, so the series is normalised by capacity.

### `Vdlin` is one fixed grid

`np.linspace(3.5, 2.0, 1000)`, monotonically **decreasing**, byte-identical for every
cell in all three batches (checked first and last cell of each). It is the x-axis for
`Qdlin`, `Tdlin` and `discharge_dQdV`. It is not stored in the pkl files;
`eda_utils_v2.VDLIN` exposes the same grid.

Note the grid starts at 3.5 V, below the 3.6 V upper cutoff, so `Qdlin` does not cover
the top of the discharge curve.

## Cycle indexing, and 2017-05-12's missing cycle 1

The page says cycle 1 was excluded from 2017-05-12. What the file actually does:

* `summary["cycle"]` still starts at **1** and runs contiguously to `n_cycles`, in all
  three batches. **Cycle numbering is not offset between batches.**
* In 2017-05-12 the row for cycle 1 is *retained as a placeholder*: all nine
  `cycles` arrays for index 0 are a 2-element vector of zeros, and
  `summary["QDischarge"][0]` is exactly `0.0`. This holds for all 46 cells.
* In 2017-06-30 and 2018-04-12 index 0 is a real cycle: 1087-sample arrays,
  `QDischarge[0] ≈ 1.07 Ah`.

So the index is aligned across batches but **the first element of every 2017-05-12
series is a zero placeholder, not a measurement**. Anything that scans a 2017-05-12
series from the start must skip it — in particular "first cycle below 0.88 Ah" returns
cycle 1 for all 46 cells if it does not. `inventory.first_valid_index` skips the
leading non-positive run and records its length in
`cell_inventory.csv:n_leading_invalid_cycles`.

## `cycle_life` is not a measured cycle life

| batch | `cycle_life − n_cycles` |
|---|---|
| 2017-05-12 | `+1` for all 46 |
| 2017-06-30 | `+1` for the 5 continuation rows; `−20 … −37` for the other 43 |
| 2018-04-12 | `+1` for 44; `NaN` for 2 |

`+1` is the else-branch of the paper's own labelling code: `LoadData.m` computes
`find(QDischarge < 0.88, 1)` and falls back to `size(cycles,2) + 1` when the strict
comparison never fires. It fires only for 2017-06-30, because only that batch was
cycled past 0.88 Ah. So for 2017-05-12 and 2018-04-12 the stored `cycle_life` carries
no information beyond the record length, and the two `NaN`s in 2018-04-12 are the two
cells the page says were stopped early (channels 33 and 41).

Cycle life is therefore recomputed in `cell_inventory.csv` with the basis recorded per
cell (`cycle_life_basis`); see the docstring of `inventory.eol_cycles`.

## Policy strings

`policy_readable` parses as `C1(Q1%)-C2` for most cells, but three deviations exist and
are flagged rather than repaired (`matr.parse_policy`):

* 2018-04-12 appends `-newstructure` to all 46 policies. Split off as
  `policy_suffix`; without that, every 2018 policy looks distinct from its 2017
  equivalent, e.g. `4.8C(80%)-4.8C-newstructure` vs `4.8C(80%)-4.8C`.
* The 5 continuation rows in 2017-06-30 have the leading current chopped:
  `80%)-3.6C` and `80%)-4C`. The 2017-05-12 segment of the same cell has the
  intact string, so the inventory takes the policy from the earlier segment.
* 2017-06-30 channel 28 stores `4C(31%)-5`, missing the second step's trailing `C`.

## Reading cost

`matr.read_batch_metadata` reads descriptors plus the whole `summary` block for a batch
in a few seconds and a few tens of MB, because it touches no `cycles` references. The
within-cycle arrays are the bulk of the 2–3 GB; `matr.BatchCycles` pulls individual
cycles on demand. This avoids the `Data/*.pkl` route entirely, which cannot be loaded
for all three batches at once on this machine (hence `eda_utils_v2._strip_cycles`).
