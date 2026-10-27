# MIT–Stanford–TRI battery dataset: data-quality audit and cleaning report

**Dataset:** Severson, Attia et al., *Data-driven prediction of battery cycle life before
capacity degradation*, Nature Energy 2019. 124 published A123 APR18650M1A LFP/graphite
cells (1.1 Ah nominal, 3.3 V), cycled to failure under fast-charging policies on a
48-channel Arbin LBT in a 30 °C chamber, in three batches dated 2017-05-12, 2017-06-30
and 2018-04-12.

**Purpose of this work:** prepare the dataset for a model of **state-of-health
evolution**, targeting the cycle at which a cell crosses **80% SOH = 0.88 Ah (80% of the
1.1 Ah nominal capacity)**. Capacity below that threshold is out of scope, as is
generalisation to other chemistries.

**Status:** audit complete; cleaning decisions taken and implemented as a derived view.
The raw `.mat` files have never been written to.

---

## 1. Headline

Starting from 140 struct rows, the dataset resolves to **135 physical cells**, of which
**128 carry an 80% SOH label** and **123 form the default trajectory training set**.

The audit tested all 21 claims made on the four dataset documentation pages:
**15 are confirmed** (several far more precisely than the pages state), **2 are
contradicted outright**, **2 are unsupported** by what the files can show, and **2 are
not testable** at the recorded sampling rate. Three of the 15 are confirmed in substance
but wrong in a stated detail — the direction of a capacity step, the sign of an artifact,
the kind of temperature inconsistency — and those are set out alongside the contradictions
in §4.2. Separately, **twelve substantive problems are present that no page mentions**,
including two channels that are simply absent and five undocumented cells whose
thermocouple signature is worse than that of one of the two cells the documentation flags.

The single most consequential finding is definitional: **the three batches do not share
an end-of-life criterion.** 2017-06-30 was cycled to 75% of nominal (0.825 Ah), the other
two to 80% (0.88 Ah). A consequence is that the `cycle_life` field stored in the structs
is **not a measurement** for 90 of 135 cells — it is the record length plus one.

---

## 2. Method

Everything was read directly from the three `.mat` files (MATLAB v7.3 / HDF5) with
`h5py`, opened read-only. Nothing was taken on trust from the upstream README or from the
pre-built `.pkl` files.

Two access problems had to be solved first.

**Barcode and channel are recoverable.** Upstream states they are "not available in the
pkl files", and `build_pkl.py` omits them. They are present in the `.mat` files as MATLAB
`string` *objects*, which h5py cannot decode directly: the field holds an MCOS header
`[0xdd000000, 2, 1, 1, object_id, class_id]` and the payload lives in
`/#subsystem#/MCOS`, element `object_id + 1`, as UTF-16 packed four characters per
`uint64`. Decoding is implemented in `matr.decode_mcos_string` and verified against two
barcodes quoted on the documentation pages. **Without this, the inventory cannot be keyed
on physical cell identity at all.**

**The pickles cannot be used.** They are 2–3 GB each and all three do not fit in memory
on the available machine. `matr.py` reads the `.mat` files lazily instead: full per-cell
metadata and summary in seconds, individual cycles on demand.

Documentation claims were encoded as data (`transcript_issues.py`) separately from any
measurement, so that "what the page says" and "what the file contains" could be compared
without entanglement. Each claim then got a dedicated check writing a tidy table.

Full schema: `schema.md`. Per-claim verdicts: `step2_findings.md`.

### Two hard limits on what is testable

- **No wall clock.** `cycles[*]["t"]` restarts at zero every cycle and there is no
  test-time or date field. Restarts are therefore not directly observable. They were
  instead located through `summary["chargetime"]`, which inflates from ~10 min to 490–1290
  min when a restart interrupts a charge — this turned out to size each gap in hours.
- **~5 s sampling.** The within-cycle sampling interval is ~5 s in all three batches. The
  IR pulse width (30 vs 33 ms) is ~1700× below this and is **not measurable at all**.

---

## 3. Dataset composition

```
struct rows                                          140   (46 / 48 / 46)
− duplicate rows for cells continued across batches   −5   →  135 physical cells
− censored in 2017-05-12 (ch 13,19,21,22,31)          −5   →  130
− removed from 2018-04-12 by upstream                 −6   →  124  (the published count)
```

| category | n | |
|---|---|---|
| complete | 122 | reached their test's criterion |
| censored | 7 | 2017-05-12 ch 13/19/21/22/31; 2018-04-12 ch 33/41 |
| continued | 5 | one physical cell spanning two batches, joined on barcode |
| flagged defective | 1 | 2017-06-30 ch 10, 170 cycles |
| no data | 4 channels | 2017-05-12 ch 4/8; **2018-04-12 ch 26/31 (undocumented)** |

Categories are exclusive by priority; the continued and defective cells also reached
their criterion. Per-cell detail: `cell_inventory.csv`.

Two traps for anyone joining these files: **barcode case is inconsistent** (2017-05-12
writes `EL…`, the other two mostly `el…`), and **2017-06-30's struct rows are not ordered
by channel** — row 1 is channel 10, row 7 is channel 1. Upstream's index-based references
(`b2c7`, `batch2_idx = [8:10,16:17]`) therefore look like different channels from the ones
the documentation names, but are the same cells.

---

## 4. Findings

### 4.1 Confirmed, and more precisely than the documentation states

| claim | measured |
|---|---|
| CV cutoff C/50, C/50, C/20 | modal minimum charge current **0.0200, 0.0200, 0.0500 C** — exact |
| Rests: 1 min+1 s / 5 min ×2 / four 5 s | one run of 55.8–60.9 s / two of 295.8 + 295.0 s / 10.1 + 4 + 4 s (two of the four merged at 5 s sampling; two cycles resolve all four) |
| Charge time ~8–13.3 min / fixed 10 / fixed 10 | **8.996–13.342 min** across policies / ~10.0 / ~10.0 |
| Channels 4, 8 have no data (2017-05-12) | absent from the struct |
| Channels 13,19,21,22,31 stopped before 80% | end at 0.913–0.969 Ah |
| Channels 33, 41 stopped before 80% (2018-04-12) | end at 0.937, 0.974 Ah |
| ch 10 dies quickly, possibly defective | 170 cycles, fewest in its batch (next genuine cell: 326) |
| ch 7 thermocouple fell off | worst temperature-rise residual in its batch, **−4.27 °C** (3rd of 140); 2.31 °C rise against 5.65 °C for ch 8 on the *identical* policy, and declining late in life |
| ch 21 thermocouple fell off | **supported on the late-life step, not the average**: T_rise falls **−2.07 °C** from early to late life, **4th of 140**. Its residual is only −0.53 °C (39th of 140), i.e. unremarkable — consistent with a thermocouple that detached part-way through, which is exactly what the page says ("found on unloading") |

**The restarts are confirmed to the hour.** Located via inflated charge time:

| batch | event | cycles | gap | evidence |
|---|---|---|---|---|
| 2017-05-12 | 1 of 2 | 13 | 6.98–7.00 h | ch 7, 15, 16 |
| 2017-05-12 | 2 of 2 | 879–902 | 4.64–4.68 h | ch 5, 44, 25 |
| 2017-06-30 | main | 246–258 | **8.19–8.47 h** | 7 cells mid-charge, 15 with capacity artifacts |
| 2017-06-30 | near-EOL | 1000 | **21.51 h** | ch 3 (EL150800460623) alone |

The page's "effectively ... around an 8-hour rest" matches to within 0.3 h, and its
identification of ch 3 for the near-EOL event is exactly right. The main 2017-06-30 event
is demonstrably **one wall-clock interruption**: the cycle at which each cell shows its
artifact is anti-correlated with that cell's cycle duration at **r = −0.993**, placing the
event at 247–253 hours into the batch for every affected cell independently.

### 4.2 Where the data departs from the page

Two of these are outright contradictions of a claim — items 1 and 3, the only two claims
in the whole audit graded **contradicted**. The other three are claims graded *confirmed*
whose page wording nonetheless gets a specific detail wrong; the claim stands, the detail
does not. The distinction matters when citing this section: a wrong detail inside a
correct claim is not the same as a false claim.

1. **"We cycle to 75% of nominal capacity (0.88 Ah)" (2017-06-30).** *(contradicted)* The two figures are
   mutually inconsistent, and **the percentage is the correct half**. Median final
   capacity by batch: 0.8807 Ah (80.07% of nominal), **0.8262 Ah (75.11%)**, 0.8804 Ah
   (80.04%). That batch really did run to 75%, roughly 20–37 cycles further than the
   others would have gone.
2. **The continuation junctions step DOWN, not up.** *(detail wrong inside a confirmed claim)* The page says the pause "lead to a
   rise in capacity upon resuming". All five drop: −0.0033, −0.0093, −0.0093, −0.0028,
   −0.0100 Ah. For three of them that is 8–18× the cell's own fade over ten cycles.
   (The pause itself was short — ~4–6 days, not months.)
3. **No C/10 cycle exists in any struct.** *(contradicted)* Scanning the first three and last three cycles
   of all 140 rows (840 cycles), the minimum peak current is **4.00 C**. Neither
   2017-06-30's claimed initial C/10 cycle nor 2018-04-12's claimed final one is present.
   Only 2017-05-12 is consistent: its cycle 1 is the excluded placeholder, and the stated
   reason — sampling rate too high — fits a slow low-rate cycle.
4. **The cycle-250 artifacts are mostly dips, not "spikes".** *(detail wrong inside a confirmed claim)* Twelve of the fourteen are
   downward (−0.02 to −0.14 Ah); the two upward ones (+0.48 Ah) are cells that were
   mid-charge and recorded two discharges in one row.
5. **2017-05-12's "inconsistent temperature control" is drift over time, not spread
   between cells.** On the between-cell measure that batch is the *tightest* of the three
   (IQR 1.45 °C). Its batch-median Tavg, however, wanders **2.97 °C** over the run — the
   largest of the three — with visible steps at cycles ~350, ~500 and ~730. The chamber
   moves under all cells at once, which a between-cell statistic cannot see. *(detail
   wrong inside a confirmed claim)*

### 4.3 Present in the data, absent from the documentation

| # | finding |
|---|---|
| U1 | **2018-04-12 is missing channels 26 and 31** entirely — no struct row, no barcode. Only 2017-05-12's absences are documented. |
| U2 | **Five of the six worst thermocouple signatures in the dataset belong to cells no page mentions.** Ranking all 140 rows by charge-heat residual, ranks 1, 2, 4, 5 and 6 are undocumented — 2017-05-12 ch 36 (−5.32 °C, 0.71 °C rise) and ch 5 (−3.93); 2018-04-12 ch 39 (−4.40, 0.82 °C) and ch 14 (−3.39); 2017-06-30 ch 4 (−3.43). Only rank 3 is documented (ch 7, −4.27), so **two undocumented cells are worse than the worst cell the pages name.** The 2018-04-12 page mentions no thermal problems at all, yet contributes two of the five. Ranks are quoted in place of a cutoff because no physical threshold separates a loose thermocouple from a cool-running cell. |
| U3 | **A third, undocumented 2017-06-30 interruption** at ~272 h, visible only through `IR = 0` on ch 1/2/3 and ch 3's isolated capacity dip at cycle 311. |
| U4 | **All 22 `IR = 0` readings sit on a restart** — none is random. This makes IR a second, independent restart detector, and it is what found U3. |
| U5 | **Cell EL150800460514 (ch 1 in both batches) is chronically glitchy:** 58 artifact cycles spread over cycles 12–851 in its first segment, then paired dip/recover events every ~10 cycles in its second. |
| U6 | **2017-05-12 ch 17 (struct index 18, barcode EL150800453240) records 2.884 Ah at cycle 40** — **2.62× nominal**, against neighbouring cycles of 1.0695 Ah. It is the largest capacity value anywhere in the dataset. |
| U7 | **Baseline temperature differs between batches by more than it varies within one:** median Tmin 30.10 / 30.03 / **31.45 °C** against a 30 °C setpoint. |
| U8 | **2017-06-30 ch 4, 7 and 8 spend 41–46% of their cycles with an inflated charge time** — 217, 222 and 216 cycles respectively **more than 3 min above that cell's own median charge time** (10.39, 11.38, 10.72 min), against a batch median of 53 such cycles. The next worst cell in the batch has 77. ch 4 and ch 7 are also that batch's two worst thermal-contact cells. |
| U9 | **`cycle_life` is not a measurement for 90 of 135 cells** — see §5. |
| U10 | **Upstream's two cleaning scripts disagree with each other**, and both drop three 2018-04-12 cells (ch 6, 7, 12) on an undocumented noise threshold. The label is not arbitrary — ch 12 and ch 6 rank 3rd and 4th of 46 on ΔQ(V) noise — but they are ~17× milder than ch 46 and ch 7 ranks 11th. The MATLAB script also calls the five-cell 2017-05-12 removal *optional*, which the Python notebook presents as unconditional. |
| U11 | **Eight policy strings are corrupted in storage:** the five continuation rows lose their leading current (`80%)-3.6C` for `3.6C(80%)-3.6C`), ch 28 stores `4C(31%)-5`, and all 46 of 2018-04-12 carry a `-newstructure` suffix that makes identical policies compare unequal across batches. |
| U12 | **The three largest late-life temperature-rise drops are the documented thermocouple-swap channels — plus one in a batch that reports no thermal problems.** 2017-06-30 ch 16 (−8.00 °C early→late), **2018-04-12 ch 15 (−7.19 °C)** and 2017-05-12 ch 15 (−6.26 °C), ranks 1–3 of 140; all three have large *positive* residuals, so they run hot on average and then fall away. The 2017 pages name 15/16 as accidentally switched with each other; the 2018-04-12 page names no thermal issue, so its ch 15 is unexplained. **Recorded as an observation only** — a swap between two channels is not something `Tmax − Tmin` per cell can prove, and nothing downstream depends on it. |

### 4.3.1 Every detector setting used above

No finding in §4.3 rests on a threshold that is not written down here. Where no cutoff
separates signal from background, the finding is stated as a **rank** instead (U2, U12).

| finding | detector | window | cutoff |
|---|---|---|---|
| U5, U6 | `QDischarge` deviation from a centred rolling median | **11 cycles** | **> 0.01 Ah** — ~10× the normal cycle-to-cycle step (~1e-3 Ah), ~50× below the artifacts it catches (0.5–1.8 Ah) |
| U8 | `chargetime` above the cell's **own** median | whole cell | **> 3 min** |
| U3, U4 | `IR` exactly `0.0` | — | none — exact equality, 22 readings |
| restart location (§4.1) | `chargetime` as elapsed wall clock | whole cell | **> 60 min** |
| U2 | `T_rise` residual from a per-batch least-squares fit of `Tmax − Tmin` on `heat_proxy`, over the first **100 cycles** | 100 cycles | **none — ranked**, 1–6 of 140 |
| U12 | median `T_rise` over the last quarter of life minus the first quarter | quarter of life | **none — ranked**, 1–3 of 140 |
| U10 | ΔQ(V) noise-to-signal: p99 of \|2nd difference of ΔQ₁₀₀₋₁₀(V)\| ÷ curve amplitude | cycles 10 and 100 | **none — ranked**; ch 46 is 85× its batch median |
| junction step (§4.2) | median of the 10 cycles each side, compared against the cell's own fade from a linear fit to the preceding 50 cycles | 10 / 50 cycles | none — all five reported |
| coulombic efficiency (§4.4) | `QD / QC` | per cycle | **> 1.01**, after an initial `> 1 + 1e-9` proved to be integration resolution |

**Two different artifact detectors exist in this repository and they are not
interchangeable.** The `is_artifact_cycle` flag in `analysis_set_cycles.csv` uses the
**0.01 Ah / 11-cycle** rule above and counts **83 cycles across 22 of 135 cells**. The
artifact counts quoted in `comparison_external_repos.md` §4.6 use a deliberately coarser
**0.03 Ah / 5-cycle** detector — chosen to match what the external repo's smoother would
actually displace, and itself tighter than `eda_utils.despike`'s 0.08 Ah — and report
**17 of 140 struct rows**. The two numbers are not comparable: different cutoff, different
window, and different denominators (135 physical cells against 140 struct rows). Neither
is wrong; any comparison between them has to say which detector was used.

### 4.4 What is *not* wrong

There are **no missing values anywhere**: not one NaN in `QDischarge`, `QCharge`, `IR`,
`Tavg`, `Tmin`, `Tmax` or `chargetime` in any of the 140 struct rows. Cycle numbering is
contiguous in every cell. `Tmax` never falls below `Tmin`. Cycle indices are **not**
offset between batches, despite 2017-05-12's missing cycle 1 — confirmed independently by
the alignment of dQ/dV peaks across batches (`fig07`).

The apparent coulombic-efficiency violation (`QD > QC` on ~2/3 of all cycles) is an
artefact of an over-tight tolerance: the median excess is **0.2 mAh on a 1.07 Ah
measurement** (CE ≈ 1.0002), which is integration resolution, not a defect. Only cycles
above CE 1.01 are physically impossible, and those turn out to be the restart artifacts.

---

## 5. The cycle-life definition problem

The documentation names a single end-of-life criterion, 0.88 Ah, but the batches did not
implement it the same way.

- **2017-05-12 and 2018-04-12 stop *at* the criterion.** Their last recorded capacity is
  0.8800–0.8834 Ah — just *above* 0.88. A strict `QDischarge < 0.88` test never fires.
- **2017-06-30 was cycled past it**, to ~0.825 Ah, so its crossing is recorded directly.

The paper's own `LoadData.m` computes `find(QDischarge < 0.88, 1)` and falls back to
`size(cycles,2) + 1` when that returns empty. For the two batches where it never fires,
**the stored `cycle_life` is that fallback** — the record length plus one, carrying no
information beyond how long the test ran. This affects all 46 cells of 2017-05-12 and 44
of 46 in 2018-04-12 (the remaining two are `NaN`, and are the censored pair).

Cycle life was therefore recomputed with the basis recorded per cell:

| basis | n | meaning |
|---|---|---|
| `strict_crossing_below_0.88Ah` | 43 | the measured crossing |
| `test_terminated_at_criterion` | 85 | the last recorded cycle, within ≤1 cycle of the crossing |
| `censored` | 7 | never reached the criterion; no label |

### A second denominator trap

The cells do not start at nominal. Median initial measured capacity is **~1.07 Ah**, so
0.88 Ah is **81.5–82.6% of each cell's own initial capacity**, not 80%.

| "80% SOH" means | threshold | cells with a usable trajectory | cells that reach the threshold |
|---|---|---|---|
| 80% of **nominal** (1.1 Ah) | 0.88 Ah | **135 of 135** | **128 of 135** (43 measured crossings + 85 terminated at criterion; the other 7 are censored) |
| 80% of each cell's **initial** capacity | ~0.853 Ah | 135 of 135 | **43 of 135** |

The two columns are different questions and were conflated in an earlier draft of this
table. *Every* one of the 135 cells has a usable SOH trajectory — a monotone-ish fade
curve that can be modelled — under either denominator; that is not what varies. What
varies is how many of them are observed to **cross** the threshold, and so carry a
supervised target: **128** under the nominal denominator, **43** under the per-cell one.

This project uses **80% of nominal**, which is what the rig was programmed against, the
convention for this cell, and a single global constant rather than a per-cell one. Under
the other reading, 92 of 135 cells would be right-censored and only one batch would remain
usable. Any write-up should say "80% of nominal (0.88 Ah)" rather than "80% SOH", because
the bare phrase is widely read as 80%-of-initial.

---

## 6. Decisions taken

| # | decision | resolution | rationale |
|---|---|---|---|
| D0 | SOH denominator | **Nominal 1.1 Ah** | §5; the alternative leaves 43 cells |
| D1 | Cycle-life definition | The 0.88 Ah crossing, basis recorded per cell | the struct field is unusable for 90 cells |
| D2 | 2017-06-30's different criterion | **Keep the batch, truncate at its crossing** | cycles below 0.88 Ah are out of scope; costs 1,179 of 21,527 cycles (5.5%) and puts all three batches on one basis |
| D3 | The 5 continued cells | **Join, but exclude from trajectory training by default** | the junction injects 1.4–5.0% of the cell's whole degradation range in a single cycle — up to 183 cycles of equivalent ageing, in the wrong direction. Retained for crossing-time work, where the junction does not touch the label |
| D4 | Censored cells | **Keep, `has_eol_label = False`** | their trajectory is valid up to where they stop; only the label is missing. Dropping them biases the distribution downward, especially the 2018-04-12 pair, which are the two longest-running cells in that batch |
| D5 | Cell selection | **Our own**, with `in_paper_124` carried | three of upstream's six 2018-04-12 removals rest on an undocumented threshold |

Nothing is masked, imputed or interpolated. Known-bad cycles are **flagged in place**
(`is_measured_cycle`, `is_artifact_cycle`, `is_restart_cycle`, `is_junction_cycle`) for
the modelling step to filter, with `is_clean_cycle` as the conjunction of all four. Full per-issue reasoning, including the options not taken:
`cleaning_plan.md`.

---

## 7. The resulting analysis set

```
analysis_set_cells.csv    135 cells × 29 columns
analysis_set_cycles.csv   113,559 cycles × 12 columns, truncated at the 80% SOH crossing
```

| | cells |
|---|---|
| physical cells | 135 |
| with an 80% SOH label | **128** |
| default trajectory training set | **123** |
| censored, no label | 7 |
| continuations, off by default | 5 |
| `in_paper_124` | 124 |

**Target:** 148–2236 cycles, median 763, spanning 1.18 decades.

**Validation** (all pass, re-run by `build_analysis_set.py`):

1. Exactly 43 **measured** cycles sit below 0.88 Ah — one per 2017-06-30 cell, the
   crossing itself — and **zero** before any cell's crossing. (46 further rows read
   below 0.88 Ah: 2017-05-12's zero-filled cycle-1 placeholders, `QD = 0.0` exactly,
   carried with `is_measured_cycle = False`. See §4.4 and `cleaning_plan.md` issue 5.)
2. The last kept cycle equals the label exactly for all 128 labelled cells.
3. `cycles_to_eol` is 0 at the crossing, never negative, NaN only for censored cells.
4. Row counts reconcile: 113,559 = Σ `n_cycles_kept`.
5. `in_paper_124` sums to exactly 124.

---

## 8. Limitations

**The batches are not exchangeable, and the differences touch the modelled quantity.**
Target medians are **841 / 481 / 1004** cycles. That is partly designed (2017-06-30 uses
the most aggressive policies) and partly protocol: CV cutoff C/20 vs C/50, different rest
schemes, and a ~1.4 °C baseline offset in 2018-04-12 all shape the measured capacity
trajectory itself. `batch_date` must stay in any model, and cells must not be split
randomly across batches.

**One chemistry only.** All 135 cells are the same part — A123 APR18650M1A, one fixture,
one chamber. Nothing here supports a cross-chemistry claim, and the two further MATR files
in this repository (`2018-02-20`, `2019-01-24`) would add cells of the same chemistry, not
coverage of others.

**The thermocouple diagnostic is approximate.** Cells are ranked by residual against
`heat_proxy = C1·Q1 + C2·(80−Q1)`, which ignores the CV tail and the common discharge. The
extremes are unambiguous; a −3.1 °C residual is not meaningfully different from −2.9 °C.

**The `Tmin` baseline proxy conflates two things** — chamber setpoint and thermocouple
contact quality — so U2 and U7 are not fully independent.

**The CV tail grows enormously with age**, from 0.315–0.330 of the charge step at cycle 10
to 0.842 / 0.863 / 0.654 at the last cycle. Late in life most of the "fast charge" is not
fast, which matters for any feature derived from charge current or time.

### Open questions the data cannot settle

1. Whether 2017-05-12's excluded cycle 1 was the initial C/10 cycle.
2. Where the other C/10 cycles went — they are in no struct, and presumably survive in the
   per-cell raw CSVs, which this copy of the dataset does not include.
3. The IR pulse width — ~1700× below the sampling interval.
4. Which 2018-04-12 cells had OCV errors; the signature is not specific to that batch.
5. Whether ch 15/16 were in fact swapped. Undetectable in 2017-05-12 (both channels run
   the same policy, so no measurement can distinguish the assignments); in 2017-06-30 the
   available test prefers the swap by 1.4%, but the same test prefers a swap *more*
   strongly in 2018-04-12 where none is claimed, so it has no specificity.
6. Absolute dates and times for any cycle, and therefore the true duration of any gap not
   caught mid-charge.
7. Why the continuation junctions step down. The rest-scheme change (1 min → 5 min) is a
   hypothesis the data is consistent with but does not establish.
8. Why channels 26 and 31 are absent from 2018-04-12.

Items 2, 4 and 8 are questions for the dataset authors; obtaining the per-cell raw CSVs
would resolve 1 and 2 together.

---

## 9. Reproducibility

The raw `.mat` files are never written to. Every table, figure and derived file in
`exploration/` is regenerated from them by:

```bash
cd "$(git rev-parse --show-toplevel)"      # the repository root
for m in inventory checks checks_cycles flags build_analysis_set \
         plots_1_6 plots_7_10 plot_analysis_set; do
    .venv/bin/python -I exploration/$m.py
done
```

This produces 20 evidence tables, 11 figures and the two analysis-set files. The
environment is pinned in the repository's `requirements.txt` (Python 3.13, numpy 2.x,
pandas 3.x, h5py 3.x) and is deliberately **not** upstream's 2019 pinned environment
(Python 3.7, h5py 2.8): the upstream `BuildPkl_Batch*.ipynb` notebooks no longer run at
all, because they use the `h5py.Dataset.value` API that h5py 3.0 removed. Exact versions
and the platform are recorded in `MANIFEST.md`.

| document | contents |
|---|---|
| `schema.md` | verified struct schema, string decoding, units |
| `cell_inventory.csv` | one row per physical cell, 41 columns |
| `step2_findings.md` | all 21 documentation claims, tested, with verdicts |
| `cleaning_plan.md` | per-issue options, trade-offs and decisions |
| `figures/README.md` | the 11 figures |
| `tables/` | 20 evidence tables |
