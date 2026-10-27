# MANIFEST

Provenance record for the analysis set. Everything below was generated on
**2026-10-27** by the rebuild loop in `README.md`, from the three raw `.mat` files and
nothing else. The rebuild is byte-reproducible: deleting every generated output and
re-running the loop reproduces all 20 tables, both analysis-set files, `cell_inventory.csv`
and all 11 figures byte-for-byte.

**Tagged `v1.0`** at commit `4e54679` (annotated tag; `refs/tags/v1.0^{}` resolves to
that commit). This manifest is the provenance record for that tag.

The three generated output files are **unchanged since `v1.0`** — the only commit after
it moved the licence-scope notes from `LICENSE` into `NOTICE.md` and updated this
paragraph. The SHA-256 values recorded below therefore still apply to the files as
they stand, and `git diff v1.0 -- exploration/analysis_set_cells.csv
exploration/analysis_set_cycles.csv exploration/cell_inventory.csv` is empty.

## Raw inputs (read-only, never modified)

Opened `mode="r"` throughout; nothing in `exploration/` writes to them.

| file | bytes | SHA-256 |
|---|---|---|
| `Data/2017-05-12_batchdata_updated_struct_errorcorrect.mat` | 3,025,320,241 | `9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba` |
| `Data/2017-06-30_batchdata_updated_struct_errorcorrect.mat` | 2,007,331,155 | `63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8` |
| `Data/2018-04-12_batchdata_updated_struct_errorcorrect.mat` | 3,236,690,412 | `62c30e413b63e6144720e016deed3661fac8468641794a5807b123fe84717998` |

`Data/` also holds `2019-01-24_...mat`, and `dataset batteries/` holds `2018-02-20_...mat`
and `2018-04-03_varcharge_...mat`. These are **other** MATR batches, outside the 124-cell
published dataset, and nothing in `exploration/` reads them.

## Generated outputs

| file | rows | bytes | SHA-256 |
|---|---|---|---|
| `exploration/analysis_set_cells.csv` | 135 cells | 34,977 | `4608880c9f3e96836685aa56383f26f9a060575a3078756ae2c4c51ba43c470e` |
| `exploration/analysis_set_cycles.csv` | 113,559 cycles | 11,244,936 | `52105f75250a2f6e7acb673a3fa7c04b0e4c3cb6cadedde9fd49972f90e823c1` |
| `exploration/cell_inventory.csv` | 139 rows (one per cell **or** empty channel slot) | 65,050 | `fe3e3115939eb1322acecda81afdf2bec54e505bb43b96a40df6836e6e3514f2` |

Row counts reconcile as follows.

* The three structs hold **46 + 48 + 46 = 140** rows.
* **5** of 2017-06-30's rows are the *second segment* of cells that began in 2017-05-12.
  Joined on barcode, they merge into their parent, leaving **135 physical cells**.
* `cell_inventory.csv` carries **139** rows: those 135 cells (`in_struct = True`), plus
  **4** channel slots that produced no cell at all (`in_struct = False`) — 2017-05-12
  ch 4 and 8, which the pages document, and 2018-04-12 ch 26 and 31, which no page
  mentions (finding U1). Per batch: 48, 43, 48.
* Of the 135 cells, **128** carry an 80%-of-nominal label and **123** form the default
  trajectory training set (`use_for_trajectory & has_eol_label`, i.e. excluding the 5
  continued cells and the 7 censored ones).

## Environment

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
| upstream reference commit | `1ef13d2` — the head of `rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation` that this audit was written against. Not a commit of this repository. |

The repository's `requirements.txt` pins exactly these versions. It is deliberately
**not** upstream's pinned environment (Python 3.7, h5py 2.8, numpy 1.22), which describes
the 2019 setup and cannot run this code: `h5py.Dataset.value` was removed in h5py 3.0, so
upstream's own `BuildPkl_Batch*.ipynb` notebooks no longer run either. See
`README.md` ("Reproducing").

## Decisions in force

These are fixed; `REPORT.md` §6 carries the full reasoning and the options not taken.

| # | decision | choice | why |
|---|---|---|---|
| D0 | SOH denominator | **Nominal 1.1 Ah** | the per-cell-initial alternative leaves only 43 labelled cells |
| D1 | Cycle-life definition | the 0.88 Ah crossing, basis recorded per cell | the struct's `cycle_life` field is unusable for 90 of 135 cells |
| D2 | 2017-06-30's different criterion | keep the batch, **truncate at its crossing** | cycles below 0.88 Ah are out of scope; costs 1,179 of 21,527 cycles (5.5%) and puts all three batches on one basis |
| D3 | The 5 continued cells | **join**, but exclude from trajectory training by default | the junction injects 1.4–5.0% of the cell's whole degradation range in one cycle, in the wrong direction |
| D4 | Censored cells | **keep**, `has_eol_label = False` | the trajectory is valid up to where it stops; only the label is missing. Dropping them biases the life distribution downward |
| D5 | Cell selection | **our own**, with `in_paper_124` carried alongside | three of upstream's six 2018-04-12 removals rest on an undocumented noise threshold |

## The split

Stored in `analysis_set_cells.csv:fold`. Fixed on **2026-10-27**; changing it invalidates
every comparison made against it.

```
SPLIT_SEED    = 20261027      (numpy default_rng)
N_FOLDS       = 5             folds 0..4
TEST_FOLD     = -1            fixed held-out cells, 27 of 135
TEST_FRACTION = 0.20          per stratum, rounded
```

Rule, in order:

1. **Unit = the physical cell**, keyed on barcode (`cell_uid == barcode`, 135 unique).
   Cycles within a cell are strongly correlated, so a cell is never split across folds —
   including both segments of a cell continued from 2017-05-12 into 2017-06-30.
2. **Strata = (`batch_date`, `has_eol_label`).** Batch, because the three differ in
   protocol and chamber behaviour; label presence, so the 7 censored cells cannot pile up
   in one fold.
3. Within each stratum, sort by barcode (so the pre-shuffle order is deterministic),
   shuffle with the seeded generator, take the first `round(0.20 × n)` as held-out test,
   then deal the remainder round-robin into folds 0–4 with a counter that **runs across
   strata**, which keeps overall fold sizes even.

Resulting sizes — test 27, folds 21–22 each, every fold within 27–36% per batch:

| fold | 2017-05-12 | 2017-06-30 | 2018-04-12 | total | unlabelled |
|---|---|---|---|---|---|
| −1 (test) | 9 | 9 | 9 | 27 | 1 |
| 0 | 8 | 7 | 7 | 22 | 1 |
| 1 | 8 | 6 | 8 | 22 | 2 |
| 2 | 7 | 7 | 8 | 22 | 2 |
| 3 | 7 | 7 | 7 | 21 | 1 |
| 4 | 7 | 7 | 7 | 21 | 0 |

A cell with `fold == -1` must not be used for training or model selection. Cells with
`has_eol_label == False` carry no target and will be dropped by any target-based metric;
they are kept because their trajectory is still valid input.

## Detector cutoffs

All of them, in one place, are in `REPORT.md` §4.3.1. Two that are easy to confuse:

* `is_artifact_cycle` — **>0.01 Ah** from a centred **11-cycle** rolling median;
  83 cycles across 22 of 135 cells.
* the artifact counts in `comparison_external_repos.md` §4.6 — a coarser **0.03 Ah /
  5-cycle** rule reporting 17 of 140 struct rows, chosen to match what a 90-cycle
  Savitzky–Golay filter would visibly displace. **Not interchangeable with the above.**

## Verification

```bash
cd "$(git rev-parse --show-toplevel)"      # the repository root
.venv/bin/python exploration/test_cell_addressing.py    # struct position != channel
for m in inventory checks checks_cycles flags build_analysis_set \
         plots_1_6 plots_7_10 plot_analysis_set; do
    .venv/bin/python exploration/$m.py
done
sha256sum exploration/analysis_set_*.csv exploration/cell_inventory.csv
```
