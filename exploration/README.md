# exploration/

Read-only exploration of the MIT–Stanford–TRI battery dataset (Severson et al., 2019)
for the purpose of **planning** a cleaning step. No data has been cleaned, modified,
dropped or relabelled; the three raw `.mat` files are opened `mode="r"` throughout.

## Read these, in order

| file | what it is |
|---|---|
| `REPORT.md` | **The consolidated cleaning and analysis report.** Read this first if you only read one thing |
| `schema.md` | The struct schema, verified from the files — including how to decode `barcode` and `channel_id`, which upstream reports as unavailable |
| `cell_inventory.csv` | **Step 1 deliverable.** 139 rows × 41 columns: the 135 physical cells plus the 4 channel slots that produced no cell |
| `step2_findings.md` | **Step 2 deliverable.** Every claim on the four dataset pages, tested, with a verdict and evidence |
| `figures/README.md` | **Step 3 deliverable.** Index of the diagnostic figures (the ten requested, plus `fig11` for the analysis set) |
| `cleaning_plan.md` | **Step 4 deliverable.** One entry per issue: evidence, options, recommendation. The five decisions are now resolved — see the table at the top |
| `analysis_set_cells.csv` | **Analysis-ready, one row per cell.** 135 cells, the 80% SOH target, flags |
| `analysis_set_cycles.csv` | **Analysis-ready, one row per cycle.** 113,559 cycles truncated at the crossing, with per-cycle quality flags |
| `MANIFEST.md` | Provenance: SHA-256 of the raw and generated files, environment versions, the decisions in force, and the fold rule |

## Code

| module | role |
|---|---|
| `matr.py` | Read-only lazy accessor for the `.mat` files. Decodes the MCOS-stored `barcode`/`channel_id` strings and parses policies |
| `transcript_issues.py` | The four dataset pages' claims, as data |
| `inventory.py` | Builds `cell_inventory.csv` |
| `checks.py`, `checks_cycles.py` | The Step 2 checks; each writes a table to `tables/` |
| `flags.py` | One shared four-class cell classification used by every figure |
| `build_analysis_set.py` | Builds the two `analysis_set_*.csv` files from the inventory and checks |
| `plotstyle.py`, `plots_1_6.py`, `plots_7_10.py`, `plot_analysis_set.py` | The figures |
| `test_cell_addressing.py` | Asserts that struct row position is **not** channel number in any batch, and that every channel named in the code resolves through the decoded `channel_id`. Run it directly |
| `probe_*.py` | One-off probes kept for provenance: how the schema and the string encoding were worked out |

Run with the repo's venv from the repo root, e.g.
`.venv/bin/python exploration/inventory.py`. (Not `-I`: isolated mode drops the
script's own directory from `sys.path`, so `import matr` fails.)
Rebuild everything:

```bash
cd "$(git rev-parse --show-toplevel)"      # the repository root
for m in inventory checks checks_cycles flags build_analysis_set \
         plots_1_6 plots_7_10 plot_analysis_set; do
    .venv/bin/python exploration/$m.py
done
.venv/bin/python exploration/test_cell_addressing.py
```

The rebuild is **byte-reproducible**: deleting every generated output and re-running the
loop reproduces all 20 tables, both analysis-set files, `cell_inventory.csv` and all 11
figures byte-for-byte. `MANIFEST.md` records the hashes.

## The per-cycle flags

`analysis_set_cycles.csv` carries four orthogonal flags plus one derived convenience
column. Nothing is masked or imputed; each reason stays separately visible.

| column | meaning |
|---|---|
| `is_measured_cycle` | the row is a measurement. False only for 2017-05-12's zero-filled cycle 1. Called `cycle_valid` until 2026-10-27 |
| `is_artifact_cycle` | `QDischarge` more than 0.01 Ah from a centred 11-cycle rolling median |
| `is_restart_cycle` | `chargetime` shows the cycle spans a test interruption |
| `is_junction_cycle` | within 2 cycles of a continuation seam |
| `is_clean_cycle` | `is_measured_cycle` and **none** of the three problem flags — the column to filter on |

`analysis_set_cells.csv` adds `fold` (seeded at 20261027, grouped by barcode, stratified
on batch and label presence; `-1` is the fixed held-out test set — see `MANIFEST.md`),
`thermocouple_fault` with its `thermocouple_evidence`, and `policy_as_stored` beside
`policy_canonical`.

## File references that point outside this repository

The documents here cite three groups of files that are **not** in this repository, and it
is worth knowing which is which before following a reference.

| referenced as | what it is |
|---|---|
| `LoadData.m`, `Load Data.ipynb`, `BuildPkl_Batch*.ipynb`, `EC_dQdV.m`, `Figure4_mac.m` | **upstream's** loading code, at <https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation>. Cited for what it does; none of it is copied here (see `../LICENSE`) |
| `build_pkl.py`, `eda_utils.py`, `eda_utils_v2.py`, `EDA.ipynb`, `EDA_v2.ipynb` | a separate, unpublished exploratory layer in the working repository: Python ports of the upstream notebooks plus an earlier pickle-based EDA. Nothing in `exploration/` imports them |
| `Data_v2/`, `dataset batteries/`, `Data/*.pkl`, the 2018-02-20 / 2018-04-03 / 2019-01-24 batches | other MATR batches and pre-built pickles held locally. Outside the 124-cell published dataset; nothing in `exploration/` reads them |

## Why this does not reuse the pre-built pickles

The upstream loader never captured `barcode` or `channel_id` — upstream's README states
they are "not available in the pkl files" — and the Step 1 inventory is keyed on both.
The pickles are also 2–3 GB each and cannot all be held in memory at once on the machine
used here. `matr.py` reads the `.mat` files directly and lazily instead, which also makes
the MCOS-stored `barcode` and `channel_id` recoverable (`schema.md`).

Three things *are* carried over from that earlier layer and are acknowledged here rather
than silently reused: `eda_utils.despike`'s spike-masking idea (at a 0.01 Ah cutoff
instead of its 0.08 Ah, and for flagging rather than plotting), its colour-blind-safe
batch palette, reproduced as `matr.BATCH_COLORS`, and the one-table-per-check pattern
from `eda_utils_v2`.
