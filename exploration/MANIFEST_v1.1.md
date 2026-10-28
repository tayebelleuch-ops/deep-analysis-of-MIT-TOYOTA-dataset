# MANIFEST v1.1 — the within-cycle extraction

Provenance record for the **additive** v1.1 work. `MANIFEST.md` remains the record for
`v1.0` and is **not edited**; this file sits beside it.

**Nothing has been tagged, pushed, uploaded or merged.** `v1.1` is a proposed tag name,
not a created tag.

## What v1.1 adds, and what it leaves alone

| | |
|---|---|
| **adds** | three HDF5 files, a per-cycle index and a per-cell table (§Outputs); nine series-validity flags; 25 evidence tables `tables/v11_*.csv`; 4 figures `figures/figv11_*.png`; `EXTRACTION_PLAN.md`, `EXTRACTION.md`, `REPORT_v1.1.md`, this file; five new scripts |
| **leaves byte-identical** | `analysis_set_cells.csv`, `analysis_set_cycles.csv`, `cell_inventory.csv`, the 20 v1.0 tables, the 11 v1.0 figures, the `v1.0` tag |
| **leaves unedited** | `REPORT.md`, `schema.md`, `cleaning_plan.md`, `step2_findings.md`, `comparison_external_repos.md`, `MANIFEST.md`, `NOTICE.md`, `README.md`, `LICENSE` |
| **changes no decision** | D0–D5 stand exactly as `MANIFEST.md` records them |

Proposed corrections to the documents above are **listed** in `REPORT_v1.1.md` §7 and
applied nowhere.

## v1.0 outputs — verified unchanged

`extract_checks.py` re-verifies these on every run and fails if any has moved:

| file | SHA-256 |
|---|---|
| `exploration/analysis_set_cells.csv` | `4608880c9f3e96836685aa56383f26f9a060575a3078756ae2c4c51ba43c470e` |
| `exploration/analysis_set_cycles.csv` | `52105f75250a2f6e7acb673a3fa7c04b0e4c3cb6cadedde9fd49972f90e823c1` |
| `exploration/cell_inventory.csv` | `fe3e3115939eb1322acecda81afdf2bec54e505bb43b96a40df6836e6e3514f2` |

Identical to `MANIFEST.md`.

## Raw inputs — read-only, never modified

Opened `mode="r"` throughout. Sizes are checked against `MANIFEST.md` on every run, and
mtimes against a baseline recorded at first extraction (`extract_out/raw_mtimes.txt`).

| file | bytes | mtime (ns) |
|---|---|---|
| `Data/2017-05-12_batchdata_updated_struct_errorcorrect.mat` | 3,025,320,241 | 1792510152000000000 |
| `Data/2017-06-30_batchdata_updated_struct_errorcorrect.mat` | 2,007,331,155 | 1792509485000000000 |
| `Data/2018-04-12_batchdata_updated_struct_errorcorrect.mat` | 3,236,690,412 | 1792510707000000000 |

The files live outside the repository and are reached through symlinks in `Data/`, which
`.gitignore` excludes by content. No copy of any raw file was made.

### Other MATR files present, and not extracted

| file | status |
|---|---|
| `Data/2019-01-24_...mat` | **truncated download** — 572,094,998 bytes on disk; h5py reports `eof = 572,094,486` against `stored_eof = 2,601,295,745`. Unreadable. 22% of the file its own superblock describes |
| `dataset batteries/2018-02-20_...mat` | readable; 47 struct rows, 26,904 cycles; **missing channel 26**; carries four `SLOWCYCLE` policies; **0 barcodes shared** with the 135 cells |
| `dataset batteries/2018-04-03_varcharge_...mat` | readable; 2 struct rows, 1,053 cycles; `VarCharge` policies; **0 barcodes shared** |

Inventoried by `probe_other_matr_files.py`; nothing reads them for data. Both readable
files carry an identical schema to the published three, so the extraction code would work
on them unchanged — they are out of scope, not out of reach.

## Outputs — hosted, never committed

Written to `exploration/extract_out/`, which contains a `.gitignore` of `*` so that no
data file can be staged by accident. **Total 2.20 GB.**

| file | bytes | SHA-256 |
|---|---|---|
| `within_cycle_2017-05-12.h5` | 797,659,714 | `8a789f4a83409ad0c1d6c214c836f2de94b63ef2e73a50722fe057c3d8a89d77` |
| `within_cycle_2017-06-30.h5` | 581,592,476 | `5f3f752d9d9a0276442fbb853941d9b212e7fffd152995b207ae6fa4a4503fae` |
| `within_cycle_2018-04-12.h5` | 823,392,641 | `bdd195323719986b3d77d4bd610c26e5e4e7c8d8ddde558b03b4696a2bcc6107` |
| `within_cycle_index.csv` | 72,846,386 | `93176963bbaaaea60a46591a3e7d1e5c3f1a04a250107eec1b754a3311b207dc` |
| `within_cycle_index_raw.csv` | 63,490,092 | `ea89da8979b4cad65f5d34fbb16dc5ca0af020dce12a03c6e8dd1e5d5908161f` |
| `within_cycle_cells.csv` | 14,379 | `ebdfca86381f7a092da9dcfdb57c90a18c716957fd37080aa8c5cd208ab3147d` |

`within_cycle_index_raw.csv` is the pre-flag intermediate; `within_cycle_index.csv` is the
published index. Only the published index needs hosting, but both are hashed so the
pipeline can be audited at either stage.

**Byte-reproducibility is demonstrated, not assumed.** Deleting all six files and
re-running the three scripts from a clean state reproduces every one byte-for-byte.
`track_times=False` is set on every HDF5 dataset; cells are written in ascending channel
order and cycles in ascending cycle order; no timestamp, hostname or library version is
written into any output.

### Row counts reconcile

```
struct cycles                                   114,738   (38,811 + 24,920 + 51,007)
− truncated past the 0.88 Ah crossing (D2)       −1,179   all 2017-06-30, flagged beyond_crossing
                                                =113,559  = analysis_set_cycles.csv, exactly
of which zero placeholders                           46   2017-05-12 cycle 1, flagged is_placeholder
native data points per series                111,868,738
total float values stored                  1,015,426,428
cycles failing at least one series check            249   across 97 of 135 cells (0.22%)
of those, is_clean_cycle = True in v1.0             171   across 54 cells -> proposed corrections
```

## Evidence

25 tables in `exploration/tables/v11_*.csv` and 4 figures in
`exploration/figures/figv11_*.png`. They are **additive**: the 20 v1.0 tables and 11 v1.0
figures are untouched, and the `v11_` prefix keeps the two sets distinguishable.

| figure | shows |
|---|---|
| `figv11_01_flagged_cycle_traces` | raw V / I / Qd for one restart, artifact and junction cycle against a series-valid cycle of the same cell |
| `figv11_02_cell17_corrupt_run` | `EL150800453240`: the corrupt run is cycles 1–53 (U15) |
| `figv11_03_bloated_cells` | the two structurally bloated cells, ch 46 and ch 17 (U16) |
| `figv11_04_qdlin_corruption` | `Qdlin` leaving the physical band, and how far (U13) |

The two largest tables are `v11_proposed_clean_cycle_corrections.csv` (171 rows — the
proposal of §7.1, **not applied**) and `v11_deltaq_feature.csv` (135 rows, the ΔQ(V)
feature per cell).

## Detector cutoffs

All of them, with the observed gap each sits in, are in `EXTRACTION.md` §5, and the ones
behind the numbered findings are repeated in `REPORT_v1.1.md` §5.1. Two that are easy to
confuse with v1.0's:

* **`is_series_valid` is not `is_clean_cycle`.** `is_clean_cycle` is a summary-level
  judgement using an **11-cycle rolling median** on `QDischarge`; `is_series_valid` is a
  **within-one-cycle** judgement on the trace itself. They disagree on 258 of 113,559
  rows in both directions, and neither supersedes the other.
* **Peak current is judged relative to each cell's own programmed rate**, not absolutely.
  An absolute 7 C ceiling flags 8,604 cycles, because 2017-05-12 runs 7C and 8C policies.

## Environment

Identical to `MANIFEST.md`; the extraction adds **no new dependency** (HDF5 was chosen
partly for that reason — `pyarrow` is not installed and pandas 3.0.6 cannot write Parquet
without it).

| component | version |
|---|---|
| Python | 3.13.5 |
| numpy | 2.5.4 |
| pandas | 3.0.6 |
| h5py | 3.16.0 (HDF5 2.0.0) |
| matplotlib | 3.11.2 |
| scipy | 1.18.1 |
| platform | Linux 6.12.107+deb13-amd64, x86_64, glibc 2.41 |
| interpreter | `.venv/bin/python` |

Extraction cost: ~18 min wall clock, peak RSS one cell at a time (~184 MiB worst case,
2018-04-12 ch 46).

## Verification

```bash
cd "$(git rev-parse --show-toplevel)"
.venv/bin/python -I exploration/test_cell_addressing.py     # v1.0: struct position != channel
rm -f exploration/extract_out/within_cycle_* exploration/extract_out/SHA256SUMS.txt
.venv/bin/python -I exploration/extract_within_cycle.py
.venv/bin/python -I exploration/extract_flags.py
.venv/bin/python -I exploration/extract_checks.py           # 67/68 checks; writes SHA256SUMS.txt
diff <(sort exploration/extract_out/SHA256SUMS.txt) <(sort /path/to/previous/SHA256SUMS.txt)
sha256sum exploration/analysis_set_*.csv exploration/cell_inventory.csv
```

## Hosting — proposed, nothing uploaded

**Decision taken: a single canonical Zenodo record.** GitHub release assets were
considered and set aside; the files are each well under the 2 GiB asset limit, but release
assets carry no DOI and are silently replaceable.

Not yet done, and **not to be done without explicit confirmation**:

1. **Sandbox rehearsal first** on `sandbox.zenodo.org` — same files, same metadata, same
   `LICENSE.txt` — to check the record renders correctly and the upload survives a 2.2 GB
   payload, then discard it. Zenodo records cannot be deleted or edited once published,
   only superseded, so a rehearsal is the only way to make the first real deposit
   reversible.
2. **Then the real record**, with: licence field `cc-by-4.0` (machine-readable); the
   Severson et al. dataset as a *related identifier* with relation **`isDerivedFrom`**;
   the "Modified:" paragraph from `EXTRACTION.md` §8 in the description; authors being
   this repository's, **not** Severson et al.'s — listing them would imply an endorsement
   CC BY 4.0 explicitly forbids.
3. **`LICENSE.txt`** (the text in `EXTRACTION.md` §8) uploaded beside the data files.
4. The minted DOI recorded back into this file and `EXTRACTION.md`.

The derived files are an adaptation of CC BY 4.0 data and carry **the dataset's terms, not
this repository's MIT licence** — the same scope rule `NOTICE.md` applies to
`analysis_set_*.csv` and `cell_inventory.csv`. This is not a new licensing position.

## Open decisions

1. **`is_clean_cycle`** — add `is_series_valid` alongside (recommended), or apply the 171
   corrections in `tables/v11_proposed_clean_cycle_corrections.csv`. See
   `REPORT_v1.1.md` §7.1.
2. **The §7.2–7.5 document corrections** — accept, reject, or amend each.
3. **Tag name** — `v1.1` is proposed and **not created**.
4. **Zenodo** — approve the sandbox rehearsal, then the real deposit.
