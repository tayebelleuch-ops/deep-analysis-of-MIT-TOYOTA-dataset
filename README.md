# A data-quality audit of the MIT–Stanford–TRI fast-charging battery dataset

An independent, read-only audit of the Severson/Attia battery dataset
([Nature Energy, 2019](https://www.nature.com/articles/s41560-019-0356-8);
data at [data.matr.io](https://data.matr.io/1/projects/5c48dd2bc625d700019f3204)),
and a documented, reproducible **analysis set** derived from it for modelling
state-of-health evolution.

Every number here was read directly from the three raw `.mat` files with `h5py`,
opened `mode="r"`. Nothing was taken on trust from the dataset documentation or from
the pre-built `.pkl` files, and **the raw files are never written to**.

---

## The dataset

124 published commercial A123 APR18650M1A LFP/graphite cells (1.1 Ah nominal, 3.3 V),
cycled to failure under 72 fast-charging policies on a 48-channel Arbin LBT in a 30 °C
chamber, in three batches dated **2017-05-12**, **2017-06-30** and **2018-04-12**. It is
the benchmark dataset for early-life battery lifetime prediction.

The audit resolves those three files to **135 physical cells**, of which **128 carry an
80%-SOH label** and **123 form the default trajectory training set**.

## Headline findings

**Two fields upstream reports as unavailable are recoverable.** `barcode` and
`channel_id` are present in the `.mat` files as MATLAB `string` *objects* — an MCOS
header pointing into `/#subsystem#/MCOS`, UTF-16 packed four characters per `uint64`.
Decoding them (`exploration/matr.py:decode_mcos_string`) is what makes the inventory
keyable on physical cell identity at all. Without it, the 5 cells that span two batches
cannot be identified.

**No struct stores its rows in channel order.** 37 of 46, 30 of 48 and 46 of 46 rows
have `index + 1 != channel`. Upstream addresses cells positionally throughout (`b1c8`,
`b3c37`, `nind = [3, 40:41]`), so every such name has to be resolved through the decoded
`channel_id` — never inferred from position. `exploration/test_cell_addressing.py`
asserts this.

**The three batches do not share an end-of-life criterion.** 2017-06-30 was cycled to
75% of nominal (median final capacity **0.8262 Ah**); the other two to 80%
(**0.8807** and **0.8804 Ah**). The 2017-06-30 documentation page states "75% of nominal
capacity (0.88 Ah)" — two mutually inconsistent figures, and the percentage is the
correct half.

**`cycle_life` in the struct is not a measurement for 90 of 135 cells.** Where the
`find(QDischarge < 0.88, 1)` test never fires — all 46 cells of 2017-05-12 and 44 of 46
in 2018-04-12 — the stored value is the fallback `size(cycles,2) + 1`, i.e. the record
length plus one. Cycle life is recomputed here with the basis recorded per cell.

**"80% SOH" has two readings, and they differ by a factor of three.** 0.88 Ah is 80% of
*nominal* but 81.5–82.6% of each cell's *own* initial capacity (median ~1.07 Ah).
Under the nominal denominator **128 of 135** cells are observed to cross the threshold;
under the per-cell one, **43 of 135**. This repository uses 80% of nominal (decision
**D0**) and says so explicitly everywhere.

**All 21 claims on the four dataset documentation pages were tested:** 15 confirmed
(several far more precisely than stated), **2 contradicted**, 2 unsupported by what the
files can show, and 2 not testable at the recorded ~5 s sampling rate. Three of the 15
are correct in substance but wrong in a stated detail.

**Twelve substantive problems are present that no documentation page mentions** (U1–U12),
including:

- **2018-04-12 is missing channels 26 and 31** entirely — no struct row, no barcode.
- **Five of the six worst thermocouple signatures belong to undocumented cells**; two of
  them are worse than the worst cell the pages name.
- **An undocumented third 2017-06-30 test interruption** at ~272 h, visible only through
  `IR = 0`.
- **All 22 `IR = 0` readings sit on a restart** — none is random, which makes `IR` a
  second, independent restart detector.
- **Eight policy strings are corrupted in storage**, and all 46 of 2018-04-12 carry a
  `-newstructure` suffix that makes identical policies compare unequal across batches.
- **The largest capacity value in the dataset** is 2017-05-12 ch 17's **2.884 Ah** at
  cycle 40 — **2.62× nominal**, against neighbouring cycles of 1.0695 Ah.

**What is *not* wrong:** there is not one NaN in `QDischarge`, `QCharge`, `IR`, `Tavg`,
`Tmin`, `Tmax` or `chargetime` in any of the 140 struct rows; cycle numbering is
contiguous in every cell; `Tmax` never falls below `Tmin`; and cycle indices are not
offset between batches. The apparent coulombic-efficiency violation on ~2/3 of all
cycles is integration resolution (median excess **0.2 mAh on a 1.07 Ah measurement**),
not a defect.

Full detail, with every detector cutoff written down, is in
**[`exploration/REPORT.md`](exploration/REPORT.md)**.

## The analysis set

Two derived files, one row per cell and one row per cycle, truncated at each cell's
80%-SOH crossing:

```
exploration/analysis_set_cells.csv     135 cells   ×  29 columns
exploration/analysis_set_cycles.csv    113,559 cycles × 12 columns
```

| | cells |
|---|---|
| physical cells | 135 |
| with an 80% SOH label | **128** |
| default trajectory training set | **123** |
| censored, no label | 7 |
| continuations, off by default | 5 |
| `in_paper_124` (the paper's published selection, carried alongside) | 124 |

Target: **148–2236 cycles**, median 763, spanning 1.18 decades.

**Nothing is masked, imputed, interpolated or smoothed.** Known-bad cycles are flagged
in place, so each reason stays separately visible:

| column | meaning |
|---|---|
| `is_measured_cycle` | the row is a measurement. False only for 2017-05-12's zero-filled cycle 1 placeholder |
| `is_artifact_cycle` | `QDischarge` departs from a centred 11-cycle rolling median by > 0.01 Ah |
| `is_restart_cycle` | `chargetime` shows the cycle spans a test interruption |
| `is_junction_cycle` | within 2 cycles of a continuation seam |
| `is_clean_cycle` | the conjunction of all four — the column to filter on for modelling |

`analysis_set_cells.csv` also carries `fold` (seeded at 20261027, grouped by barcode,
stratified on batch and label presence; `-1` is the fixed held-out test set),
`thermocouple_fault` with its `thermocouple_evidence`, and `policy_as_stored` beside
`policy_canonical`.

The five cleaning decisions in force (**D0**–**D5**) and the options not taken are set
out in [`exploration/cleaning_plan.md`](exploration/cleaning_plan.md); the provenance
record, including the SHA-256 of every generated file and the fold rule, is in
[`exploration/MANIFEST.md`](exploration/MANIFEST.md).

## What is in this repository

| path | contents |
|---|---|
| [`exploration/REPORT.md`](exploration/REPORT.md) | **The consolidated audit and cleaning report. Read this first.** |
| `exploration/schema.md` | The verified struct schema, string decoding, units |
| `exploration/step2_findings.md` | All 21 documentation claims, tested, with verdicts and evidence |
| `exploration/cleaning_plan.md` | One entry per issue: evidence, options, trade-offs, decision |
| `exploration/MANIFEST.md` | Provenance: SHA-256 of raw and generated files, environment, decisions, fold rule |
| `exploration/comparison_external_repos.md` | The audit set against two external repositories that model this data |
| `exploration/analysis_set_cells.csv`, `analysis_set_cycles.csv` | The analysis set |
| `exploration/cell_inventory.csv` | One row per physical cell or empty channel slot, 41 columns |
| `exploration/tables/` | 20 evidence tables, one per check |
| `exploration/figures/` | 11 diagnostic figures, indexed in `figures/README.md` |
| `exploration/*.py` | The code: `matr.py` (read-only lazy `.mat` accessor), `inventory.py`, `checks*.py`, `flags.py`, `build_analysis_set.py`, the plotting modules, and `test_cell_addressing.py` |
| `exploration/external_comparison/` | Scripts re-deriving every external-repository number from the raw files |
| `Data/` | **Not committed.** Where the three raw `.mat` files go — see [`Data/README.md`](Data/README.md) |

The modelling code for the original paper is under an academic licence and is not here,
and is not needed by anything in this repository.

## Reproducing

**1. Get the raw data.** Download the three batch files from
<https://data.matr.io/1/projects/5c48dd2bc625d700019f3204> into `Data/`:

| file | bytes | SHA-256 |
|---|---|---|
| `2017-05-12_batchdata_updated_struct_errorcorrect.mat` | 3,025,320,241 | `9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba` |
| `2017-06-30_batchdata_updated_struct_errorcorrect.mat` | 2,007,331,155 | `63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8` |
| `2018-04-12_batchdata_updated_struct_errorcorrect.mat` | 3,236,690,412 | `62c30e413b63e6144720e016deed3661fac8468641794a5807b123fe84717998` |

`Data/README.md` has a copy-pasteable `sha256sum -c` block.

**2. Set up the environment.** Python 3.13 with numpy 2.x / pandas 3.x / h5py 3.x:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**3. Rebuild everything.** From the repository root:

```bash
for m in inventory checks checks_cycles flags build_analysis_set \
         plots_1_6 plots_7_10 plot_analysis_set; do
    .venv/bin/python exploration/$m.py
done
.venv/bin/python exploration/test_cell_addressing.py
```

That regenerates the 20 evidence tables, the 11 figures, `cell_inventory.csv` and both
analysis-set files, and runs `build_analysis_set.py`'s five validation checks. The
rebuild is **byte-reproducible**: `exploration/MANIFEST.md` records the hashes, and
deleting every generated output and re-running the loop reproduces them byte-for-byte.

Peak memory is a few hundred MB — `exploration/matr.py` reads the `.mat` files lazily,
precisely so the 2–3 GB pickles are never needed.

## Open questions for the dataset authors

Three of these the files cannot settle, and all three are questions of record rather
than of interpretation:

1. **Where are the other C/10 cycles?** Scanning the first three and last three cycles
   of all 140 struct rows (840 cycles), the minimum peak current is **4.00 C** — no C/10
   cycle exists in any struct. 2017-06-30's claimed initial one and 2018-04-12's claimed
   final one are both absent. They presumably survive in the per-cell raw CSVs, which
   this copy of the dataset does not include.
2. **Which 2018-04-12 cells had the OCV errors** the page refers to? The signature is
   not specific to that batch.
3. **Why are channels 26 and 31 absent from 2018-04-12?** There is no struct row and no
   barcode for either, and no page mentions them. An undocumented absence might mean
   those tests failed in a way that affected their neighbours.

Two further items the authors may wish to correct on the dataset pages:

4. The 2017-06-30 page's **"75% of nominal capacity (0.88 Ah)"** is internally
   inconsistent; the measured median final capacity for that batch is 0.8262 Ah
   (75.11% of nominal), so the percentage is right and the Ah figure is not.
5. The 2017-05-12 page says the mid-test pause "lead to a rise in capacity upon
   resuming"; **all five continued cells step down** (−0.0033 to −0.0100 Ah).

**Obtaining the per-cell raw CSVs would resolve (1) together with the open question of
whether 2017-05-12's excluded cycle 1 was the initial C/10 cycle.**

Three further questions are limits of the recorded data rather than requests: the IR
pulse width is ~1700× below the sampling interval and is not measurable; there is no
wall clock in any struct, so absolute dates and gap durations are only recoverable where
a restart interrupted a charge; and whether channels 15/16 were swapped cannot be
settled by any per-cell temperature statistic. `exploration/REPORT.md` §8 sets all of
these out.

## Licensing

Three different sets of terms apply to three different things in this repository.

**The dataset** — the three raw `.mat` files — is distributed by Toyota Research
Institute under **CC BY 4.0**, as stated on TRI's own catalog page
(<https://data.matr.io/>, entry *"Data-driven prediction of battery cycle life before
capacity degradation"*, 23 January 2019). CC BY 4.0 permits redistribution and
adaptation, including commercially, with attribution and an indication of changes. The
raw files are **not** redistributed here; download them from the source.

**The derived files in this repository** — `analysis_set_cells.csv`,
`analysis_set_cycles.csv`, `cell_inventory.csv` and `exploration/tables/*.csv` — are
adaptations of that CC BY 4.0 data and are redistributed here under **CC BY 4.0**,
attributed as:

> Derived from Severson, K. A., Attia, P. M., Jin, N., Perkins, N., Jiang, B., Yang, Z.,
> Chen, M. H., Aykol, M., Herring, P. K., Fraggedakis, D., Bazant, M. Z., Harris, S. J.,
> Chueh, W. C., & Braatz, R. D. (2019). *Data-driven prediction of battery cycle life
> before capacity degradation.* Nature Energy, 4(5), 383–391.
> Dataset: <https://data.matr.io/1/projects/5c48dd2bc625d700019f3204> (CC BY 4.0).
> Modified: cells joined on barcode, cycle life recomputed, records truncated at the
> 0.88 Ah crossing, quality flags added. See `exploration/REPORT.md` §6.

**The code in this repository** is our own and is licensed under the terms in
[`LICENSE`](LICENSE).

**Upstream's loading code** — the MATLAB scripts and `BuildPkl_Batch*.ipynb` notebooks
at
<https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation>
— carries **no licence file**, so no rights to copy or adapt it are granted. None of it
is copied, vendored or imported here; `exploration/matr.py` is an independent reader
written against the verified schema in `exploration/schema.md`. Where upstream's cell
selection is referenced (`PAPER_EXCLUDED`, `UPSTREAM_POSITIONAL`), it is referenced as a
list of cell identifiers — a fact about the published dataset, not as code.

## Citing this work

See [`CITATION.cff`](CITATION.cff). Any use of the data should cite Severson et al.
(2019) and the dataset, as above.
