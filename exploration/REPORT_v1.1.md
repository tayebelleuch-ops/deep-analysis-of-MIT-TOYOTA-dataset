# REPORT v1.1 — audit of the within-cycle data

**Scope.** v1.0 audited what the struct `summary` block says about each cycle. This audits
the nine **within-cycle series** that v1.0 did not carry, extracted at full coverage:
114,738 cycles, 1,015,426,428 float values. Schema, keys and flags:
[`EXTRACTION.md`](EXTRACTION.md). Hashes and environment:
[`MANIFEST_v1.1.md`](MANIFEST_v1.1.md).

**The data.** Zenodo record `23984188`, version DOI `10.5281/zenodo.23984188`, version
label `1.1.0` — an **unpublished draft** at the time of writing, so the DOI does not
resolve and the files are not publicly downloadable yet. Nothing in this report depends
on that: every number here was computed from the local extraction output, whose SHA-256 is
in `MANIFEST_v1.1.md`.

**This document proposes; it does not edit.** No decision (D0–D5) changed, the three v1.0
CSVs are byte-identical to `v1.0`, and `REPORT.md`, `schema.md`, `cleaning_plan.md` and
`MANIFEST.md` are untouched. Corrections to them are listed in §7 for the maintainer to
accept or reject. The proposed per-cycle corrections to `is_clean_cycle` are in
`tables/v11_proposed_clean_cycle_corrections.csv` and are **not applied**.

---

## 1. Headline

**The within-cycle data contains defects that no summary-level detector can see.** Of the
113,559 cycles in the analysis set, **171 are `is_clean_cycle = True` in v1.0 yet fail a
check on their own series**, across 54 cells. The reverse also holds: 87 cycles v1.0
flags have perfectly ordinary series.

Three results carry most of the weight.

1. **The interpolated voltage-domain fields go physically impossible on 48 cycles across
   32 cells**, reaching **+1,431 Ah and −4,030 Ah on a 1.1 Ah cell**. Thirty-four of the
   48 are `is_clean_cycle = True`. Anyone computing ΔQ(V) without filtering gets values
   three orders of magnitude out of range (U13).
2. **Two undocumented multi-cell events in 2017-05-12** — cycles 141–166 across 7 cells
   and 655–684 across 5 — with normal charge time and no `IR = 0` reading, i.e. invisible
   to *both* v1.0 restart detectors (U14).
3. **`EL150800453240`'s corrupt run is cycles 1–53, not cycle 40 alone** (U15). v1.0
   flags one cycle of that cell; 51 more are corrupt and marked clean.

Against that, several v1.0 and documentation claims are **confirmed at full coverage**
where they had rested on samples — most sharply, **no C/10 cycle exists in any of the
114,692 measured cycles**, where `REPORT.md` §4.2 had scanned 840.

---

## 2. Method

Everything was read from the extracted HDF5 files, which `extract_checks.py` verifies
against a fresh read of the raw `.mat` on every run. Per-cycle diagnostics were computed
from the **float64** source during extraction, so no number here depends on the float32
narrowing of eight of the nine published series.

Each detector states its threshold and its window, and **every window is one cycle** —
these are properties of a single series, which is exactly what makes them independent of
the v1.0 detectors (`is_artifact_cycle` is an 11-cycle rolling median on `QDischarge`).
All cutoffs sit in observed gaps in the measured distributions; the gaps are quoted in
[`EXTRACTION.md`](EXTRACTION.md) §5. Where no gap exists, the quantity is **reported and
not flagged**, following the rule `REPORT.md` §4.3.1 sets for U2 and U12.

**Two of my own first attempts were wrong and the data said so**, which is why the
thresholds are set from distributions rather than from physics alone:

* an absolute 7 C ceiling on peak current flagged **8,604 cycles** — because 2017-05-12
  contains **7C and 8C charging policies**, which `schema.md` does not mention. The check
  is now relative to each cell's own programmed rate, and flags 3.
* a strict "time must increase" test flagged **258 cycles across 86 cells** whose worst
  backward step is **−2.9e-11 s** — float64 rounding in MATLAB's own arithmetic. With a
  −60 µs tolerance it flags **0**.

---

## 3. Confirmed, at full coverage

| claim | v1.0 basis | measured here |
|---|---|---|
| **No C/10 cycle exists in any struct** (`REPORT.md` §4.2 item 3, graded *contradicted*) | first and last 3 cycles of 140 rows = 840 cycles | **all 114,692 measured cycles.** Minimum peak \|I\| is **4.0006 C** (2017-05-12 and 2017-06-30) and **4.3642 C** (2018-04-12). **Zero** cycles anywhere have a peak below 1.0 C. The contradiction is now total, not sampled |
| Rest scheme: 1 min / 5 min ×2 / four 5 s | a sample | median longest rest run per cycle: **55.8 s / 295.8 s / 10.1 s** — reproduces `REPORT.md` §4.1 exactly |
| `discharge_dQdV` is the derivative of `Qdlin` | asserted | RMS residual against `d(Qdlin)/d(Vdlin)` is **0.0569 Ah/V**, **0.99%** of the curve's own amplitude. The field is what it claims to be |
| Cycle indices are not offset between batches | the visual alignment of fig07 | dQ/dV peak voltage at cycle 100: medians **3.1486 / 3.1426 / 3.1547 V**, per-batch σ 0.004–0.010 V. Batch medians span **0.0120 V = 8 of 1000 grid steps** |
| The CV tail grows with age (`REPORT.md` §8) | ends only | median CV share by quartile of life: 0.338→0.488, 0.371→0.674, 0.284→0.350. Monotone in all three batches |
| The series and the summary agree | untested | ∫(−I dt) − `QDischarge`: median **+0.51 mAh** on a ~1.07 Ah measurement (0.05%) |

---

## 4. Where the data departs from v1.0 and from the documentation

### 4.1 The v1.0 flags, tested against the series

On the 113,559 rows of the analysis set:

| | `is_series_valid` False | True |
|---|---|---|
| **`is_clean_cycle` False** | 78 | 87 |
| **`is_clean_cycle` True** | **171** | 113,223 |

| v1.0 flag | n | of which series-invalid | |
|---|---|---|---|
| `is_restart_cycle` | 13 | **13 (100%)** | every restart cycle is confirmed by its own series |
| `is_artifact_cycle` | 83 | 21 (25.3%) | most capacity artifacts have an ordinary trace — the defect is in the value, not the series |
| `is_junction_cycle` | 25 | **0 (0%)** | junctions are *between*-cycle discontinuities; the series are normal, as they should be |
| `~is_measured_cycle` | 46 | 46 (100%) | the placeholders |

The `is_junction_cycle` result is a positive check on orthogonality: a within-cycle
detector should not fire on a between-cycle seam, and it does not.

### 4.2 Claims whose numbers move

1. **The 1000-sample cap** (`comparison_external_repos.md` §4.7). That section probed 420
   cycles and reported "59% of probed cycles lose data, averaging 9.4%". At full
   coverage: **50.4% of cycles truncated, 6.55% of points lost on average**. The
   per-batch ordering it reports is exactly right, and its central point stands — the
   loss is batch- and age-dependent, and worst in the batch doing the most work:

   | batch | % cycles truncated | mean % points lost | Q1 → Q4 (points lost) |
   |---|---|---|---|
   | 2017-05-12 | 88.0 | 5.62 | 8.11 → 1.62 (**falls** with age) |
   | 2017-06-30 | **92.6** | **21.13** | 19.19 → **23.23** (rises with age) |
   | 2018-04-12 | 1.15 | 0.14 | 0.10 → 0.28 |

   The aggregate gap is a sampling-weight artifact: three cycles per cell weights
   2018-04-12's 46 rows equally with the rest, when that batch holds 44% of all cycles and
   is the one barely affected. Its "late" figure of 30.0% for 2017-06-30 is also not
   comparable to my 23.2%: theirs is the last cycle, mine the last quartile.

2. **The CV share** (`REPORT.md` §8). Under a CV definition keyed to the **fixed 3.6 V**
   cutoff (±5 mV), weighted by sample interval:

   | | `REPORT.md` §8 | measured here |
   |---|---|---|
   | at cycle 10 | 0.315–0.330 | **0.342 / 0.374 / 0.319** (medians by batch) |
   | at the last cycle | 0.842 / 0.863 / 0.654 | **0.676 / 0.825 / 0.645** |

   2018-04-12 agrees closely (0.645 vs 0.654) and 2017-06-30 reasonably (0.825 vs 0.863);
   2017-05-12 differs materially (0.676 vs 0.842). The definitions are not identical —
   `cleaning_plan.md` records that an earlier per-cycle-maximum keying produced spurious
   zeros — and mine takes the last **series-valid** cycle. **Reported as a disagreement,
   not resolved**: the qualitative claim (the tail grows, and is largest in 2017-06-30) is
   confirmed either way.

3. **Coulombic efficiency** (`REPORT.md` §4.4). The median excess `QD − QC` is **0.117
   mAh** over series-valid cycles, against the 0.2 mAh that section quotes. Both support
   its conclusion — this is integration resolution, not a defect. From the *integrated
   series* rather than the summary fields, CE has a far wider spread (17,264 cycles above
   1.01 against 73), which is a property of integrating a multi-step charge, not of the
   cells.

---

## 5. New findings

Numbered on from `REPORT.md`'s U1–U12. Observation-only unless the evidence is decisive.

| # | finding |
|---|---|
| **U13** | **The interpolated fields go physically impossible on 48 cycles across 32 cells**, with `Qdlin` reaching **+1,431 Ah** (2017-06-30 ch 38, cycle 247) and **−4,030 Ah** (2018-04-12 ch 46, cycle 368) on a 1.1 Ah cell. **34 of the 48 are `is_clean_cycle = True` in v1.0.** On the same cycles the *summary* capacity artifact is ~1%. The interpolation onto `Vdlin` blows up when a row's voltage trace is non-monotonic — which is what a spliced or interrupted row produces — and nothing at summary level registers it. Any ΔQ(V) feature computed without filtering these mixes in values three orders of magnitude out of range. |
| **U14** | **Two undocumented multi-cell events in 2017-05-12.** Clustering the U13 cycles by cycle number (window 30 cycles, wide enough to hold the 13-cycle spread of the known 2017-06-30 event): cycles **141–166 on 7 cells** (ch 5, 12, 23, 33, 38, 43, 45) and **655–684 on 5 cells** (ch 2, 5, 25, 39, 43). Both have **ordinary charge times** (9.1–13.3 min) and **no `IR = 0` reading**, so they are invisible to both v1.0 restart detectors — the same way U3 was found only through `IR = 0`. All 12 cycles are `is_clean_cycle = True`. The same clustering recovers the two documented events (2017-05-12 cycles 12–13 on 5 cells; 2017-06-30 cycles 246–258 on 14 cells), which is the control. **Observation only**: a common cause is consistent with the clustering but not established — the structs carry no wall clock. |
| **U15** | **`EL150800453240` (2017-05-12 ch 17, struct index 18): the corrupt run is cycles 1–53, not cycle 40.** 53 of its 690 cycles fail a series check and **51 of them are `is_clean_cycle = True`**. The mechanism is visible directly: cycle 30 holds a normal cycle (1,042 samples, t 0→50.8 min, ending at the 2.0 V floor), then a **48.3 h gap**, then 749 samples of a later cycle beginning at 3.38 V. The rows **splice fragments recorded 36–48 h apart**. Through the run, `V_max` climbs 3.66 → 5.04 → **6.61 V** and the sampling interval collapses from 5 s to **0.01 s**. Cycle 54 onward is textbook-normal (50.84 min, 4.996 s, V_max 3.600). This supersedes U6 in extent: the 2.884 Ah reading is one symptom of a 53-cycle fault. (`figv11_02`) |
| **U16** | **`EL150800737364` (2018-04-12 ch 46) carries 48 cycles at more than 5× its batch's median sample count**, up to **61,901 samples** against a batch median of 730, scattered across its whole life rather than in one run. **46 of its cycles are `is_clean_cycle = True` yet series-invalid**, against the 3 capacity artifacts v1.0 records. This gives the 2018-04-12 page's "noisy voltage profiles, likely electronic connection error" a structural cause, and shows it affects ~16× more cycles than the summary-level evidence suggested. (`figv11_03`) |
| **U17** | **`Qdlin` systematically understates discharge capacity by a median 31.9 mAh (~3%)**, because `Vdlin` starts at **3.5 V**, below the 3.6 V charge cutoff, so the top of the discharge curve is outside the grid. Per batch: −36.4 / −49.4 / −27.4 mAh. `schema.md` notes the grid starts low; this quantifies the consequence. Anyone treating `Qdlin[-1]` as the cycle's discharge capacity inherits a 3% bias that varies by batch. |
| **U18** | **The sampling interval is not uniformly ~5 s.** `REPORT.md` §2 states ~5 s for all three batches. Measured per cycle: **96.3% / 54.2% / 89.9%** of cycles have a median interval within ±0.5 s of 5 s — so **nearly half of 2017-06-30's cycles do not**, with a 1st percentile of **0.648 s**. The conclusion that section draws (the IR pulse is far below resolution) is untouched: even 0.65 s is 20× a 33 ms pulse. |
| **U19** | **The pooled ΔQ(V) correlation is stronger than any single batch's.** log₁₀Var(ΔQ₁₀₀₋₁₀(V)) against log₁₀ cycle life gives **ρ = −0.925** pooled over 127 cells, but **−0.945 / −0.815 / −0.785** within 2017-05-12 / 2017-06-30 / 2018-04-12. Between-batch spread in both feature and target inflates the headline number; a model validated across batches will not see −0.93. This is consistent with `REPORT.md` §8's insistence that `batch_date` stay in any model, and quantifies the cost of ignoring it. |
| **U20** | **2018-04-12's series-to-summary capacity residual is 40× the other two batches'.** ∫(−I dt) − `QDischarge` has a median of **+17.0 mAh** there against **+0.41 and +0.42 mAh** in 2017-05-12 and 2017-06-30. Something differs in how that batch's discharge capacity is accumulated or integrated. **Observation only** — 17 mAh is 1.6% of capacity and does not threaten any v1.0 conclusion, but it is a systematic batch effect in a quantity that ought to be protocol-independent. |
| **U21** | **Four cells' dQ/dV minimum sits on the 2.0 V grid endpoint** — 2017-05-12 ch 40, 2017-06-30 ch 16, 2018-04-12 ch 13 and ch 38 — with magnitudes −12.2 to −19.2 Ah/V, an interpolation edge artifact rather than a phase-transition peak. Excluding them tightens the cross-batch peak-alignment σ from 0.17–0.24 V to **0.004–0.010 V**. Anyone locating the dQ/dV peak by `argmin` must exclude the endpoints. |

### 5.1 Every detector setting used above

| finding | detector | window | cutoff |
|---|---|---|---|
| U13, U14 | `Qdlin` ∉ [−0.10, 1.50] Ah, or `Tdlin` ∉ [0, 80] °C, or `dQdV` ∉ [−200, 0] Ah/V | one cycle | as stated; nominal capacity is 1.1 Ah and the failures reach ±4,030 Ah |
| U14 clustering | out-of-band cycles grouped by cycle number | **30 cycles** | ≥ **4 cells** to count as a candidate event; chosen to hold the known 2017-06-30 event's 13-cycle spread |
| U15, U16 | `dt_max > 600 s`; `t_end > 240 min`; `n_samples > 5 × batch median`; `V ∉ [1.80, 3.70]` | one cycle | each sits in an observed gap — see `EXTRACTION.md` §5 |
| U17 | `Qdlin[-1] − QDischarge` | one cycle | none — a distribution, reported as median and per-batch medians |
| U18 | median within-cycle `dt` | one cycle | ±**0.5 s** of the stated 5.0 s |
| U19 | Pearson ρ of log₁₀Var(ΔQ₁₀₀₋₁₀(V)) on log₁₀ cycle life | cycles 10 and 100 | none — a correlation |
| U20 | ∫(−I dt) − `QDischarge` | one cycle | none — per-batch medians |
| U21 | `argmin(discharge_dQdV)` landing on index 999 | one cycle, cycle 100 | exact |
| reported, **not flagged** | peak \|I\| 1.10–1.50× the programmed rate (418 cycles, 4 cells); one duplicated timestamp (35 cycles, 29 cells) | one cycle | **no gap separates these from the background**, so they are graded observations |

### 5.2 The two structurally bloated cells, in detail

Stage 0 found that cycle-length bloat is confined to exactly two cells. They turn out to
have **two different faults**, and the distinction matters because only one of them is a
recording error of the kind v1.0's detectors could ever have caught.

| | `EL150800737364` — 2018-04-12 ch 46 | `EL150800453240` — 2017-05-12 ch 17 |
|---|---|---|
| cycles in the cell | 1,389 | 690 |
| cell median samples / batch median | 703 / 730 — **normal** | 1,037 / 1,065 — **normal** |
| longest cycle | **61,901** samples | **31,104** samples |
| cycles over 5× the batch median | 48 | 5 |
| cycles failing any series check | 49 | 53 |
| of those, `is_clean_cycle = True` in v1.0 | **46** | **51** |
| capacity artifacts v1.0 records | 3 | 1 |
| affected cycle range | **1–1,217, spread evenly** (11/11/11/13 per quarter) | **2–53, one contiguous run** |
| dominant failing check | `series_length_plausible` (45 of 46) | `series_time_contiguous` **and** `series_duration_plausible` (51 of 51 each) |
| `t_end` on affected cycles | 32.6 – 4,825.5 min | 2,165.6 – 4,074.6 min |
| `V` on affected cycles | 1.889 – 3.652 V — **within the cutoffs** | **0.736 – 6.606 V** — grossly outside |

**ch 46 is an over-sampling fault that recurs for the cell's whole life.** Its median cycle
is perfectly ordinary; the fault is episodic, firing roughly every 25–30 cycles and
producing rows of up to 59,356 samples. Crucially its voltage never leaves the cutoffs, so
the *values* are plausible throughout — only the sample count is not. That is consistent
with the 2018-04-12 page's "noisy voltage profiles, likely electronic connection error"
and with `cleaning_plan.md` issue 9's finding that this cell's ΔQ(V) roughness is 85× its
batch median. What is new is the **extent**: 46 cycles are affected rather than the 3 the
capacity artifacts record, and they run the length of the cell rather than clustering.
This cell already carries `exclude_from_deltaq_features = True`, which remains the right
call.

**ch 17 is a splicing fault confined to the start of the record.** Every one of its 51
corrections fails *both* time checks, and the mechanism is directly visible (U15): a
normal cycle, a 36–48 h gap, then a fragment of a later cycle in the same row. Thirteen of
them also breach the voltage cutoffs, reaching 6.606 V and dropping to 0.736 V — values
no LFP/graphite cell can produce. From cycle 54 the cell is textbook-normal for its
remaining 637 cycles.

**Neither cell should be dropped.** ch 46's capacity trajectory is sound and ch 17's is
sound from cycle 54 on; both already carry cell-level flags in v1.0 for other reasons.
What this adds is a per-cycle handle: `is_series_valid` marks exactly which of their
cycles are unusable, where v1.0 could only mark the cell. For ch 17 specifically, any
feature read at cycle 10 or cycle 100 is affected at cycle 10 and not at cycle 100 — which
is why §6 flags its ΔQ(V) feature as computed from a spliced row.

---

---

## 6. The paper's early-prediction feature

Computed on **cycles 10 and 100** in the analysis set's numbering. No per-batch shift is
applied and none is needed: cycle numbering is not offset between batches, and
2017-05-12's missing cycle 1 is a *retained placeholder*, not a deletion — so cycle 10 is
the 10th recorded cycle in every batch. **All 135 cells have both cycles.** No model was
fitted and nothing was tuned.

ρ of log₁₀Var(ΔQ₁₀₀₋₁₀(V)) against log₁₀ cycle life:

| basis | n | ρ |
|---|---|---|
| all labelled cells with both cycles | 128 | **−0.9200** |
| minus `exclude_from_deltaq_features` (`EL150800737364`, 2018-04-12 ch 46) | 127 | −0.9254 |
| minus that cell **and** the shortest-lived cell | 126 | −0.9233 |
| `in_paper_124` | 124 | **−0.9274** |
| `in_paper_124` minus its shortest-lived cell | 123 | −0.9254 |

**The paper reports two different values for the same panel:** **ρ = −0.92** in the Fig. 2c
panel label and **−0.93** in that figure's caption. It does not say which is which. Both
are reproduced here, and the difference is a matter of basis rather than of method:
our 128 labelled cells give **−0.9200**, and the paper's own 124-cell selection gives
**−0.9274**, which rounds to −0.93.

**Which cell is excluded, in each case.** The paper's caption says "in b and c, the
shortest lived battery is excluded" — it names no cell. On our definitions the
shortest-lived cell is **`EL150800460605`, 2017-06-30 ch 10, cycle life 148**, which is the
cell the pages call possibly defective (`REPORT.md` §4.1: 170 recorded cycles, fewest in
its batch). Excluding it *weakens* the correlation slightly (−0.9254 → −0.9233 on our
basis, −0.9274 → −0.9254 on the paper's), so the paper's exclusion is not what produces
−0.93. The separate exclusion `exclude_from_deltaq_features` removes **`EL150800737364`,
2018-04-12 ch 46**, on the ΔQ(V)-noise grounds of `cleaning_plan.md` issue 9.

One caveat on the feature itself: **`EL150800453240`'s cycle-10 series is invalid** (it
falls inside the U15 corrupt run), so its ΔQ(V) feature is computed from a spliced row.
It is the only cell of the 135 for which that is true, and it is retained above rather
than silently dropped. Per-batch ρ is in U19 and is materially weaker than the pooled
figure.

---

## 7. Corrections

**Four factual corrections have been applied**, in a separate docs commit for review:
the two column counts in `REPORT.md` §7, and in `schema.md` the `I` range, the native
length range and the 7C/8C policies behind them (marked **APPLIED** below).

**Everything else here remains a proposal and is applied nowhere** — in particular every
interpretive item: the cause of ch 46's bloat, the two undocumented 2017-05-12 events,
the CV-share disagreement and the `is_clean_cycle` corrections. Those are worded as
observations by design; they rest on inference the data supports but does not settle.

### 7.1 To `analysis_set_cycles.csv`

**171 cycles across 54 cells are `is_clean_cycle = True` but fail a series check.** The
full list, with the failing check and the evidence for each row, is
`tables/v11_proposed_clean_cycle_corrections.csv`. The largest contributors are
`EL150800453240` (51 cycles, U15) and `EL150800737364` (46 cycles, U16).

**Recommendation: do not change `is_clean_cycle`.** Add `is_series_valid` alongside it
instead, as this extraction does. The two flags answer different questions — one about a
cycle's capacity relative to its neighbours, one about the integrity of its own trace —
and collapsing them would lose the distinction that makes each useful. A caller wanting
both can take the conjunction. This is a decision for the maintainer; the data supports
either choice and the correction list is ready if the other is preferred.

### 7.2 To `schema.md`

| § | says | proposed |
|---|---|---|
| `cycles` **APPLIED** | `I` ranges "≈ −4.0 … +5.0 for a 4C discharge / 5C charge" | full range **−12.213 … +8.169 C**. 2017-05-12 runs **7C and 8C** charging policies (`7C(30%)-3.6C`, `8C(15%)-3.6C` and four more, across 12 cells); the −12.2 C extreme is one of three flagged 2018-04-12 discharge outliers |
| `cycles` **APPLIED** | `t` native length "~750–1100" | medians **1,065 / 1,269 / 730**; 2017-06-30's p75 is 1,421; the maximum anywhere is **61,901** |
| `Vdlin` | "`np.linspace(3.5, 2.0, 1000)`, byte-identical for every cell (checked first and last cell of each)" | true to **1 ulp, not bitwise** — 15 of 1000 points differ by ≤4.44e-16. Now verified on **all 140 rows**, not two per batch |
| `cycles` | `Qdlin`, `Tdlin`, `discharge_dQdV` length "**1000**" | 1000 **except on the 46 placeholder rows, where it is 2** — consistent with the cycle-indexing section, but the length table does not say so |

### 7.3 To `REPORT.md`

| § | says | proposed |
|---|---|---|
| §2 | "The within-cycle sampling interval is ~5 s in all three batches" | modal 5 s, but only **54.2%** of 2017-06-30's cycles are within ±0.5 s of it (U18). The IR-pulse conclusion is unaffected |
| §7 **APPLIED** | `analysis_set_cycles.csv` … **12 columns**; `analysis_set_cells.csv` … **29 columns** | **13** and **31**. `cell_inventory.csv`'s stated 41 is correct |
| §4.4 | "no missing values anywhere" (summary fields) | extend: **zero NaN in any of the nine within-cycle series**, over all 114,738 cycles — and `t[0] == 0` in every cycle, and time is strictly increasing in every cycle beyond float64 rounding |
| §4.4 | median CE excess "0.2 mAh" | **0.117 mAh** over series-valid cycles; the conclusion is unchanged |
| §4.2 item 3 | "no C/10 cycle exists" — from 840 cycles | now from **all 114,692 measured cycles**; minimum peak \|I\| 4.0006 C, zero cycles below 1.0 C |
| §8 | CV share 0.315–0.330 at cycle 10; 0.842 / 0.863 / 0.654 at the last | see §4.2 item 2 — the definitions differ and the numbers should be quoted with the definition attached |
| §4.3 | U6 (the 2.884 Ah reading) | supersede with **U15**: the fault is cycles 1–53, not cycle 40 |
| open q. 8 | "Why channels 26 and 31 are absent from 2018-04-12" | add that **2018-02-20 is also missing channel 26** (47 rows: 1–25, 27–48), consistent with a dead channel rather than two unrelated failures. 2018-02-20 *has* a channel 31, so that absence stands unexplained |
| open q. 2 | "Where are the other C/10 cycles?" | add that **2018-02-20 carries four `SLOWCYCLE` policies** (`3.6C(80%)-3.6C(SLOWCYCLE` and three more), a policy string absent from all three published batches — so slow cycles exist in the programme, just not here |

### 7.4 To `MANIFEST.md` and `CLAUDE.md`

Both describe `Data/2019-01-24_...mat` as another MATR batch. It is a **truncated
download**: h5py cannot open it, `eof = 572,094,486` against `stored_eof = 2,601,295,745`
— 22% of the file its own HDF5 superblock describes. Nothing reads it, so nothing is
affected, but it should not be listed as usable. The other two non-published files are
readable and carry an identical schema: `2018-02-20` (47 rows, 26,904 cycles) and
`2018-04-03_varcharge` (2 rows, 1,053 cycles), **neither sharing any barcode with the 135
cells**.

### 7.5 To `comparison_external_repos.md`

§4.7's aggregate ("59% of probed cycles, averaging 9.4%") should be restated at full
coverage as **50.4% and 6.55%**, with the note that its per-batch and per-age structure is
confirmed. See §4.2 item 1.

---

## 8. What is not wrong

* **No NaN anywhere in the within-cycle data** — zero, in all nine series over all 114,738
  cycles. v1.0 established this for the summary fields; it now holds throughout.
* **`t` resets to exactly 0.0 at the start of every cycle**, all 114,738 of them. The field
  is per-cycle elapsed time, with no test-time leakage.
* **Time increases strictly within every cycle.** The worst backward step anywhere is
  −2.9e-11 s, which is float64 rounding; 35 measured cycles contain one duplicated
  timestamp each, reported and not treated as invalidating.
* **The six native series always share one length**, on every cycle, without exception.
* **`discharge_dQdV` really is d(`Qdlin`)/d(`Vdlin`)**, to 0.99% of the curve's amplitude.
* **The `Vdlin` grid is one grid**, byte-identical across all 140 struct rows — stronger
  than the first-and-last-cell check `schema.md` records.
* **99.78% of cycles pass every series check** (114,489 of 114,692 measured). The defects
  above are concentrated: 97 cells carry at least one, and two cells carry 102 of the 249.

---

## 9. Limitations

* **No wall clock, still.** U14's clusters are *consistent with* common events but cannot
  be shown to be: `t` resets every cycle and there is no date field. The clustering window
  (30 cycles) and the 4-cell minimum are stated choices, not derived ones.
* **The CV-share disagreement in §4.2 is not resolved.** Two defensible definitions give
  different numbers for 2017-05-12; I report mine with its definition attached rather than
  declare `REPORT.md` §8 wrong.
* **U20 has no explanation.** A 40× batch difference in a protocol-independent residual is
  reported because it is real and reproducible, not because its cause is known.
* **The series-validity flags are not a cleaning recipe.** They say a trace is not
  trustworthy, not what to do about it. Nothing here is masked, imputed or smoothed, and
  §7.1 recommends adding the flag rather than altering v1.0's.
* **float32 for eight of nine series.** Measured worst case 6.0e-08 relative error, three
  to five orders below every tolerance used here, and every number in this report was
  computed from the float64 source — but the *published arrays* are float32.

---

## 10. Reproducibility

```bash
cd "$(git rev-parse --show-toplevel)"
.venv/bin/python -I exploration/extract_within_cycle.py
.venv/bin/python -I exploration/extract_flags.py
.venv/bin/python -I exploration/extract_checks.py
for m in v11_structure v11_voltage_domain v11_artifacts; do
    .venv/bin/python -I exploration/$m.py
done
```

Deleting every output and re-running reproduces all six data files byte-for-byte; the
three v1.0 CSVs are untouched and still hash to their `MANIFEST.md` values. Evidence
tables are `tables/v11_*.csv`; figures are `figures/figv11_*.png`. Environment and hashes:
[`MANIFEST_v1.1.md`](MANIFEST_v1.1.md).
