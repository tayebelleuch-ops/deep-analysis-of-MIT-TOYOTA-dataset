# Step 2 — every page claim tested against the files

Verdicts: **confirmed** / **partly confirmed** / **not confirmed** (measured, and the
data does not support it) / **not testable** (the files cannot answer it) /
**contradicted** (the data says something different).

Evidence files are in `exploration/tables/`. Nothing below has been applied to the
data; this is a measurement record.

Every detector cutoff and window used below is tabulated in `REPORT.md` §4.3.1. Where no
cutoff meaningfully separates signal from background, findings are stated as **ranks**
rather than as threshold crossings.

Two limits bound what was testable at all:

* **No wall clock.** `cycles[*]["t"]` restarts at 0 each cycle and there is no
  test-time or date field. Restarts are therefore detected indirectly — but
  `summary["chargetime"]` (0–80% SOC duration, minutes) turned out to be a precise
  detector: a restart that interrupts a charge inflates it from ~10 min to several
  hundred, which sizes the gap in hours.
* **~5 s sampling.** The within-cycle sampling interval is ~5 s in all three
  batches (`tables/cycle_metrics_life.csv:dt_median_s`), so sub-second features are
  invisible.

---

## 2017-05-12

| # | Page claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Cycle 1 absent from the struct | **confirmed**, with a mechanism the page does not describe | `tables/cycle_indexing.csv` |
| 2 | Channels 4 and 8 have no data | **confirmed** | `cell_inventory.csv` (`in_struct=False`) |
| 3 | Channels 13, 19, 21, 22, 31 stopped before 80% | **confirmed** | `cell_inventory.csv` (`censored`) |
| 4 | Channels 15 and 16 have swapped thermocouples | **not testable** | `tables/thermocouple_swap.csv` |
| 5 | Computer restarted twice | **confirmed**, both events located | `tables/time_gaps.csv` |
| 6 | Chamber temperature inconsistent | **confirmed** — as drift over time, not spread between cells | `tables/chamber_drift.csv`, `fig05` |

**1 — cycle 1.** The row is *retained as a placeholder*, not deleted: for all 46 cells
the nine `cycles` arrays at index 0 are a 2-element vector of zeros and
`summary["QDischarge"][0]` is exactly `0.0`. `summary["cycle"]` still starts at 1 and
runs contiguously in all three batches, so **cycle indices are not offset between
batches** — but the first element of every 2017-05-12 series is a fabricated zero.
Consequence: "first cycle below 0.88 Ah" returns cycle 1 for all 46 cells unless the
leading entry is skipped.

**5 — the two restarts.** Located by inflated `chargetime` (normal ≈ 11 min):

| event | cycle | cells affected | gap |
|---|---|---|---|
| first | 13 | ch 7, 15, 16 | 6.98 – 7.00 h |
| second | 879 – 902 | ch 5, 44, 25 | 4.64 – 4.68 h |

Exactly two events, as claimed. Only cells that happened to be mid-charge register a
gap; the rest of the batch shows nothing, which is why a capacity-spike search finds
almost nothing here (only 4 cells, `tables/capacity_spikes.csv`).

**IR = 0 is a second, independent restart detector.** All 22 cycles in the dataset
that record `IR = 0.0` exactly (19 in 2017-05-12, 3 in 2017-06-30, none in 2018-04-12)
sit on a restart event — none is random:

| batch | IR = 0 at cycles | matches |
|---|---|---|
| 2017-05-12 | 12–13 (11 cells) | restart event 1 (cycle 13) |
| 2017-05-12 | 848–909 (8 cells) | restart event 2 (cycles 879–902) |
| 2017-06-30 | 311, 313, 331 (ch 3, 2, 1) | **nothing the chargetime detector found** |

The last row is a **third 2017-06-30 interruption**, affecting only the three 3.6C
continuation cells and on no page. It did not show up in `tables/time_gaps.csv` because
none of those cells happened to be mid-charge, and it is the same event that produces
ch 3's isolated capacity dip at cycle 311. Those three cells complete a cycle in ~52.5
min against ~60 min for the rest of the batch — their slower charge is more than offset
by a much shorter CV tail — so they reach a higher cycle number by any given wall-clock
moment, placing this event ~272 h into the batch, roughly 22 h after the main one.
Evidence: `tables/ir_zero_cycles.csv`.

**6 — chamber temperature.** This needs two measurements, because they disagree and
only one supports the page.

*Between cells*, 2017-05-12 is the **tightest** of the three batches: per-cell baseline
`Tmin` spans 1.57 °C (sd 0.38) against 2.57 °C for 2017-06-30 and 1.81 °C for
2018-04-12, and its between-cell IQR at a fixed cycle, 1.45 °C, is the lowest of the
three. On this reading the claim looks unsupported — and that was my first verdict.

*Over time*, it is clearly right. Fig 5 (row 1, left) shows the whole batch stepping
together: a jump of ~2 °C at cycle ~350, a sharp drop at ~500, another rise at ~730.
Tracking the batch-median `Tavg` over cycles where at least half the batch is still
running, 2017-05-12 wanders **2.97 °C** — the largest of the three (2017-06-30 1.98 °C,
2018-04-12 2.58 °C). That is the chamber moving under every cell at once, which is what
inconsistent temperature control looks like; it is invisible to a between-cell
statistic because it affects all cells equally. **Verdict: confirmed.**

---

## 2017-06-30

| # | Page claim | Verdict | Evidence |
|---|---|---|---|
| 7 | ch 1, 2, 3, 5, 6 are continuations of 2017-05-12 cells | **confirmed** by barcode; but the capacity step at the junction goes the **opposite way** to the page | `cell_inventory.csv`, `tables/continuation_junction.csv`, `fig02` |
| 8 | Restart near cycle 250 ≈ an 8-hour rest, spikes across most cells | **confirmed**, quantitatively | `tables/time_gaps.csv`, `tables/capacity_spikes.csv` |
| 9 | Second restart near EOL affects ch 3 (EL150800460623) | **confirmed** | `tables/time_gaps.csv` |
| 10 | ch 10 (EL150800460605) dies quickly, possibly defective | **confirmed** | `cell_inventory.csv` |
| 11 | Thermocouples on ch 7 and 21 fell off | **confirmed**, by two different signatures: ch 7 on the average residual, ch 21 on the late-life step | `tables/thermocouple_outliers.csv` |
| 12 | ch 15 and 16 switched | **not confirmed** (test lacks specificity) | `tables/thermocouple_swap.csv` |
| 13 | "75% of nominal capacity (0.88 Ah)" | **contradicted**: the percentage is right, the Ah figure is wrong | `tables/eol_criterion.csv` |

**7 — the join.** Case-insensitive barcode matching gives exactly five cells shared
between 2017-05-12 and 2017-06-30, and they are channels 1, 2, 3, 5, 6 **in both
batches**, exactly as the page says. (Upstream's `b2c7, b2c8, b2c9, b2c15, b2c16`
look like different channels but are the same cells — 2017-06-30's struct rows are
not ordered by channel.) The batch-1 segments end at 0.971–1.043 Ah, far above the
0.88 Ah criterion, confirming they were paused rather than finished.

**But the capacity step at the junction contradicts the page.** The 2017-05-12 page says
the pause "lead to a rise in capacity upon resuming the tests". Comparing the median of
the 10 cycles each side of the junction, **all five cells drop**:

| barcode | ch | step at junction | that cell's fade over 10 cycles |
|---|---|---|---|
| EL150800460514 | 1 | **−0.0033 Ah** | −0.0008 Ah |
| EL150800460486 | 2 | **−0.0093 Ah** | −0.0006 Ah |
| EL150800460623 | 3 | **−0.0093 Ah** | −0.0005 Ah |
| EL150800464977 | 5 | −0.0028 Ah | −0.0043 Ah |
| EL150800464865 | 6 | **−0.0100 Ah** | −0.0012 Ah |

For ch 2, 3 and 6 the step is 8–18× the cell's own ageing rate, so it is a genuine
discontinuity rather than continued fade; only ch 5's step is within its normal drift.
A rest normally lets a lithium-ion cell recover capacity, so the direction is
surprising. One candidate explanation that the data is consistent with but does not
prove: the resumed cells ran under 2017-06-30's rest scheme (5 min after charge instead
of 2017-05-12's 1 min), and a longer relaxation before discharge would reduce the
measured discharge capacity slightly. **This matters for anyone joining the segments:
the join introduces a step of up to 0.01 Ah that is an artefact of the protocol change,
not cell ageing.**

**8 — the cycle-250 restart is decisively one wall-clock event.** Seven cells were
mid-charge and record a gap of **8.19–8.47 h** at cycles 248–253, matching the page's
"effectively ... around an 8-hour rest" to within ~0.3 h. Fifteen cells show a
one-cycle capacity artifact at cycles 246–258. The correlation between the artifact's
cycle number and the cell's cycle duration is **r = −0.993**: faster-cycling cells
reach a higher cycle number by the same instant. Converting back, every affected cell
places the event at **247–253 hours** into the batch (ch 3 excepted, at 272 h).

One qualification: the page says "spikes" in capacity, implying upward. **Twelve of
the fourteen artifacts near cycle 250 are downward dips** of −0.02 to −0.14 Ah; only
two are upward (ch 45 at cycle 248, +0.48 Ah; ch 28 at cycle 253, +0.47 Ah) — and
those two are themselves among the seven cells with an 8-hour charge gap, i.e. they
recorded two discharges inside one cycle row.

**9 — ch 3.** A **21.51-hour** gap at cycle 1000 on barcode EL150800460623, and it is
the only cell in the dataset with a gap that large. The page's cell identification is
exactly right. The capacity effect is modest (a −0.0085 Ah step), not the dramatic
spike the wording suggests.

**10 — ch 10.** 170 cycles, the fewest in the batch; the next-lowest genuine cell has
326 and the median is ~700. Barcode `el150800460605` matches the page up to case.

**11 — thermocouples.** Discriminant: `T_rise` = median(`Tmax` − `Tmin`), residual
against a per-batch fit on `heat_proxy = C1·Q1 + C2·(80−Q1)` (relative I²R heat over
the fast-charge portion).

* **ch 7: confirmed.** Worst residual in the batch, **−4.27 °C** (T_rise 2.31 °C vs
  5.65 °C for ch 8 on the identical 4.8C(80%)-4.8C policy), and its T_rise *falls*
  0.63 °C from early to late life — consistent with detaching during the test, which
  is how it came to be discovered only on unloading.
* **ch 21: confirmed, on the other column.** Its *average* residual is ordinary —
  −0.53 °C, 39th of 140, T_rise 6.04 °C against a batch median of 6.82 °C — and on that
  measure alone this claim was initially recorded as unsupported. That was the wrong
  column to read. A thermocouple that falls off **part-way through** produces a step
  down, not a low average, and ch 21 has the **4th largest late-life drop of all 140
  rows: −2.07 °C** from the first quarter of life to the last. The page says the
  detachment was "found on unloading", i.e. late; the late-life step is the signature
  that claim predicts, and it is present. Ranked rather than thresholded, because no
  cutoff separates a detaching thermocouple from a cell that simply cools as it ages.

**12 — the ch 15/16 swap.** Here the two channels do run different policies, so the
assignment is in principle testable, and swapping them does fit marginally better
(SSE 4.898 vs 4.965 — a 1.4% improvement). That is not evidence. The same test
applied to 2018-04-12, where **no page claims any swap**, prefers the swapped
assignment far more strongly (2.50 vs 4.39). A test that fires harder on a negative
control than on the positive case cannot adjudicate this, so: **unresolved, and not
resolvable this way.**

**13 — the 75% / 0.88 Ah contradiction, resolved.** Cells that ran to completion:

| batch | last recorded QD (median) | as % of 1.1 Ah nominal | n below 0.88 Ah |
|---|---|---|---|
| 2017-05-12 | 0.8807 Ah | **80.07%** | 0 / 36 |
| **2017-06-30** | **0.8262 Ah** | **75.11%** | **43 / 48** |
| 2018-04-12 | 0.8804 Ah | **80.04%** | 0 / 44 |

**The "75%" is the correct half of the sentence and "(0.88 Ah)" is the error.**
2017-06-30 really was cycled to 75% of nominal = 0.825 Ah, ~20–37 cycles further than
the other two batches would have gone. The three batches do **not** share an
end-of-life definition, and 0.88 Ah is not a common stopping point.

Direct consequence, already visible in Step 1: 2017-05-12 and 2018-04-12 *stop at*
0.88 Ah (last cycle 0.8800–0.8834 Ah, just above), so `QDischarge < 0.88` never fires
and the struct's `cycle_life` field for those two batches is only `n_cycles + 1` —
the else-branch of the paper's own `LoadData.m`.

---

## 2018-04-12

| # | Page claim | Verdict | Evidence |
|---|---|---|---|
| 14 | Channels 33 and 41 stopped before 80% | **confirmed** (0.937, 0.974 Ah) | `cell_inventory.csv` |
| 15 | ch 46 has noisy voltage profiles | **confirmed** | `tables/deltaq_roughness.csv`, `fig07` |
| 16 | OCV errors caused temporary pauses in some cells | **not confirmed as specific to this batch** | `tables/cycling_pauses.csv` |
| 17 | A final C/10 cycle was performed | **contradicted**: no C/10 cycle exists in any struct | `tables/cycle_metrics_ends.csv` |

**15 — ch 46.** The raw within-cycle voltage trace does *not* single this cell out:
its second-difference is ~2× the batch median (1.58e-4 vs 7.3e-5), but ch 48 matches it
(1.60e-4). That measurement is dominated by the sampling grid and was my first,
mistaken, basis for calling the claim unconfirmed.

The noise shows up unmistakably in the **voltage-domain difference curve**, which is
where it actually matters. Measuring the 99th-percentile roughness of
ΔQ₁₀₀₋₁₀(V) relative to that cell's own ΔQ amplitude:

| batch | median noise-to-signal | worst cell |
|---|---|---|
| 2017-05-12 | 0.011 | ch 43, 0.147 |
| 2017-06-30 | 0.006 | ch 41, 0.186 |
| **2018-04-12** | **0.004** | **ch 46, 0.316** |

ch 46's oscillation is **32% of its own degradation signal** — 85× its batch median and
8× the next-worst cell in that batch — and is plainly visible in Fig 7 (bottom right),
where it swings ±0.01 Ah against a ΔQ amplitude of 0.008 Ah while its neighbours are
smooth. **Verdict: confirmed**, and the cell is unusable for any ΔQ(V)-based feature.
Separately, ch 46 is also the only cell in its batch with capacity artifacts (+0.063
and +0.069 Ah at cycles 597–598, −0.012 Ah at cycle 1064). Upstream's `LoadData.m`
removes it "upfront" for "a problem with the data collection".

Two cells in the other batches have comparably poor noise-to-signal — 2017-05-12 ch 43
(0.147) and 2017-06-30 ch 41 (0.186) — and neither is mentioned on any page.

**16 — OCV pauses.** Using "cycles whose chargetime exceeds this cell's own median by
>3 min": 44 of 46 cells in this batch have at least one, worst case 25 cycles and
+13.6 min. But 2017-05-12 (37/46, up to 50 cycles) and 2017-06-30 (48/48, up to 222
cycles) are the same or worse, so the signature is not specific to this batch and
cannot identify "some cells". What this batch does *not* have is any restart-scale
interruption: **zero cycles anywhere in 2018-04-12 exceed 60 min of charge time**,
versus 6 in 2017-05-12 and 8 in 2017-06-30.

**17 — the C/10 cycles.** The explicit question was whether an initial C/10 cycle
exists here as well as the stated final one. Scanning the first three and last three
recorded cycles of **all 140 struct rows** (840 cycles), the minimum peak |I| is
**4.00 C** — every cycle in every struct is a fast-charge cycle. So:

* 2018-04-12: **neither** a final nor an initial C/10 cycle is in the struct.
* 2017-06-30: the page claims an initial C/10 cycle; cycle 1 peaks at 4.00–6.04 C. Not present.
* 2017-05-12: the page claims an initial C/10 cycle, and index 0 is precisely the
  2-sample zero placeholder. Consistent with the C/10 cycle having been the excluded
  cycle 1 — and the page's stated reason, "the sampling rate for this cycle was
  initially too high", fits a slow low-rate cycle. Suggestive, not provable.

The C/10 cycles presumably survive in the per-cell raw CSVs, which this dataset copy
does not include.

---

## Across batches

| # | Page claim | Verdict | Measured |
|---|---|---|---|
| 18 | CV cutoff C/50, C/50, C/20 | **confirmed exactly** | modal min charge current 0.0200 C, 0.0200 C, **0.0500 C** |
| 19 | Rests: 1 min + 1 s / 5 min ×2 / four 5 s | **confirmed within sampling resolution** | see below |
| 20 | IR pulse width 30 / 30 / 33 ms | **not testable** | sampling interval ~5 s ≈ 1700× the pulse |
| 21 | Charge time 0–80% SOC: ~8–13.3 min / fixed 10 / fixed 10 | **confirmed** | 8.99–13.36 / 10.01–13.43 / 10.04–11.04 min |

**19 — rests**, measured as runs of |I| ≤ 0.01 C within a cycle:

| batch | page | measured |
|---|---|---|
| 2017-05-12 | 1 min, then 1 s | **one** rest, 55.8–60.9 s. The 1 s rest is below the ~5 s sampling interval. |
| 2017-06-30 | 5 min, then 5 min | **two** rests, 295.8 s + 295.0 s |
| 2018-04-12 | four 5 s rests | **three** runs, 10.1 s + 4 s + 4 s in most cycles; two cycles resolve all four as 4\|4\|4\|4. The 10 s run is the two adjacent rests (after 80% SOC and after the IR test) merged at this sampling rate. |

**21 — charge time.** 2017-05-12 varies by policy from 8.996 min (5.4C(80%)-5.4C) to
13.342 min (3.6C(80%)-3.6C), matching the page's "~8 to 13.3 minutes" almost exactly.
The other two are fixed at ~10.0 min. The apparent 13.43 min outlier in 2017-06-30 is
ch 3 — a continued cell still running its 2017-05-12 3.6C policy, so "fixed at 10
minutes" describes the 43 new cells only.

**CV fraction of the charge step** (median, `cv_fraction_of_charge`, measuring the
charge samples within 5 mV of the 3.6 V cutoff): **0.315–0.330** at cycle 10 in all
three batches, rising by the last cycle to **0.842** (2017-05-12), **0.863**
(2017-06-30) and **0.654** (2018-04-12). At mid-life the batches have already diverged
sharply — 0.352 / 0.747 / 0.294 — because 2017-06-30 charges hardest and was cycled
furthest. Late in life most of the "fast charge" is not fast at all.

---

## Undocumented findings (nothing on any page)

| id | finding | evidence |
|---|---|---|
| U1 | **2018-04-12 is missing channels 26 and 31** entirely — no struct row, no barcode. Only 2017-05-12's ch 4/8 absence is documented. | `cell_inventory.csv` |
| U2 | **Five of the six worst thermocouple signatures belong to cells no page mentions.** Ranking all 140 rows by T_rise residual, ranks 1, 2, 4, 5 and 6 are undocumented: 2017-05-12 ch 36 (−5.32 °C, T_rise 0.71 °C) and ch 5 (−3.93); 2018-04-12 ch 39 (−4.40, T_rise 0.82 °C) and ch 14 (−3.39); 2017-06-30 ch 4 (−3.43). Rank 3 is the documented ch 7 (−4.27), so **two undocumented cells are worse than the worst documented one**. The 2018-04-12 page mentions no thermocouple problems at all, yet supplies two of the five. Stated as ranks: no physical cutoff separates a loose thermocouple from a cool-running cell. | `tables/thermocouple_outliers.csv` |
| U2b | **The three largest late-life T_rise drops are the 15/16 channels** — 2017-06-30 ch 16 (−8.00 °C), 2018-04-12 ch 15 (−7.19 °C), 2017-05-12 ch 15 (−6.26 °C), ranks 1–3 of 140, all with large *positive* residuals. The 2017 pages call 15/16 swapped with each other; 2018-04-12 claims no thermal problem, so its ch 15 is unexplained. **Observation only** — per-cell `Tmax − Tmin` cannot prove a swap (see claim 12). | `tables/thermocouple_outliers.csv` |
| U3 | **Cell EL150800460514 (ch 1 in both batches) has chronic single-cycle capacity artifacts** — 58 cycles flagged at **>0.01 Ah from a centred 11-cycle rolling median**, spread over cycles 12–851 in its 2017-05-12 segment (max deviation 0.46 Ah), and recurring paired dip/recover events every ~10 cycles (528/529, 538/539, 548/549, 618/619) in its 2017-06-30 segment. Not mentioned anywhere. | `tables/capacity_spikes.csv` |
| U4 | **2017-05-12 ch 17 (struct index 18, barcode EL150800453240) records 2.884 Ah at cycle 40** — **2.62× nominal**, against neighbouring cycles of 1.0695 Ah. It is the largest capacity value anywhere in the dataset, and the largest deviation found by the **>0.01 Ah / centred 11-cycle median** detector. The 1.8146 Ah figure in `capacity_spikes.csv` is the DEVIATION from the local median, not the recorded value. (`eda_utils.despike`'s docstring records the same artifact under its struct-index name, b1c18.) | `tables/capacity_spikes.csv` |
| U5 | **Baseline temperature differs between batches by more than it varies within one.** Median `Tmin` early: 30.10 °C (2017-05-12), 30.03 °C (2017-06-30), **31.45 °C** (2018-04-12) — a ~1.4 °C offset against within-batch spreads of 1.6–2.6 °C, for a chamber nominally at 30 °C. Caveat: `Tmin` is a cell-surface reading, so it conflates chamber setpoint with thermocouple contact quality. | `tables/temperature.csv` |
| U6 | **Upstream's own two cleaning scripts disagree, and both drop three cells no page justifies.** `Load Data.ipynb` removes six 2018-04-12 cells as "noisy"; three of them (ch 6, 7, 12) terminated normally at 0.8804–0.8806 Ah. `LoadData.m` reaches the same set by a different route (ch 46 "upfront", then a `QDischarge(end) > 0.885` censoring filter, then `nind = [3, 40:41]` "noisy Batch 8 batteries"), and additionally calls the five-cell 2017-05-12 removal *optional*, which the Python notebook presents as unconditional. | `Load Data.ipynb`, `LoadData.m` |
| U7 | **Barcode case is inconsistent between files** (2017-05-12 all `EL…`; 2017-06-30 43 of 48 `el…`; 2018-04-12 45 of 46 `el…`). A case-sensitive join would still have found the five continuations by luck — they kept the uppercase form — but it is fragile. | `schema.md` |
| U8 | **Two policy strings are corrupted in storage**: the five continuation rows in 2017-06-30 lose their leading current (`80%)-3.6C` for `3.6C(80%)-3.6C`), and ch 28 stores `4C(31%)-5`, missing the second step's trailing `C`. All 46 of 2018-04-12's policies carry a `-newstructure` suffix that makes them compare unequal to their 2017 equivalents. | `cell_inventory.csv` |
| U10 | **A third, undocumented interruption in 2017-06-30** at ~272 h, visible only through `IR = 0` on ch 1, 2 and 3 and through ch 3's capacity dip at cycle 311. | `tables/ir_zero_cycles.csv` |
| U11 | **2017-06-30 ch 4, 7 and 8 spend 41–46% of their cycles with an inflated charge time** — ch 4 217 cycles (41.4%), ch 7 222 (45.6%), ch 8 216 (43.4%), counting cycles **more than 3 min above that cell's own median** charge time (10.39, 11.38, 10.72 min). Batch median is 53 such cycles; the next worst cell has 77. ch 4 and ch 7 are also the batch's two worst thermal-contact cells. | `tables/cycling_pauses.csv`, `fig10` |
| U9 | **`cycle_life` is not a measurement for two of three batches** — it equals `n_cycles + 1` for all of 2017-05-12 and 44 of 46 in 2018-04-12 (the remaining two are `NaN`, and are ch 33/41, the censored pair). | `schema.md` |

## Claims the files cannot settle

* The IR pulse width (30 vs 33 ms) — ~1700× below the sampling interval.
* Whether ch 15/16 were in fact swapped, in any batch. Undetectable in 2017-05-12
  (identical policies); in 2017-06-30 the available test has no specificity.
* Whether 2017-05-12's excluded cycle 1 was the initial C/10 cycle.
* Which 2018-04-12 cells had OCV errors.
* Absolute test dates/times for any cycle, and therefore the true duration of any gap
  not caught mid-charge.
