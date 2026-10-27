# Cleaning plan — proposed, nothing applied

Nothing in this document has been done to the data. The raw `.mat` files have been
opened read-only throughout; `exploration/` contains only derived tables, figures and
the code that produced them.

Evidence references: figures in `exploration/figures/`, tables in
`exploration/tables/`, per-cell rows in `exploration/cell_inventory.csv`, schema in
`exploration/schema.md`, per-claim verdicts in `exploration/step2_findings.md`.

Throughout, **the unit of analysis is the cell**. There are 135 physical cells. Cycle
counts (~110,000 rows) are not sample sizes.

A recurring theme below: several of these issues are only problems *for some uses*. A
cell with a detached thermocouple is fine for a capacity-based analysis and useless for
a thermal one. So most recommendations are **flag, don't drop** — the inventory already
carries the flags, and a modelling step can filter on them. Dropping is recommended
only where a cell would silently corrupt a result.

---

## Decisions — RESOLVED 2026-10-27

The stated goal is **predicting when 80% SOH is crossed**, as a model of SOH evolution;
capacity below that threshold is out of scope, and cross-chemistry generalisation is out
of scope. That settles all five, as built into `build_analysis_set.py`:

| # | Decision | Resolution |
|---|---|---|
| **D0** | SOH denominator (new — surfaced by the goal) | **Nominal 1.1 Ah**, so 80% SOH = 0.88 Ah. Against each cell's own initial capacity (~1.07 Ah), 0.88 Ah is 81.5–82.6%, and only 43 of 135 cells would ever reach 80%. Nominal is also one global constant rather than a per-cell one. |
| **D1** | Cycle life definition | The 0.88 Ah crossing: `cycle_life_cycles`, basis recorded per cell. 128 of 135 cells carry a label. |
| **D2** | 2017-06-30 | **Kept and truncated** at its crossing. Costs 1179 of 21527 cycles (5.5%) in that batch. `batch_date` stays as a factor. |
| **D3** | The 5 continued cells | **Joined but excluded from trajectory training by default** (`use_for_trajectory = False`): the junction injects 1.4–5.0% of the cell's whole degradation range in one cycle. Kept for crossing-time work, where the junction does not touch the label. |
| **D4** | Censored cells | **Kept**, `has_eol_label = False`. Valid trajectories, no crossing label. |
| **D5** | Cell selection | **Our own**, with `in_paper_124` carried for optional comparison. ch 46 marked `exclude_from_deltaq_features`. |

The original framing of each decision is preserved in the issue entries below.

### The five as originally posed

| # | Decision | Why it's yours |
|---|---|---|
| **D1** | Is cycle life defined at 0.88 Ah, or at "the cycle the test stopped"? | They are the same number for 2 of 3 batches and differ by 20–37 cycles for the third. See issue 1. |
| **D2** | Does 2017-06-30 stay in a pooled dataset at all, given it used a different end-of-life criterion? | Issue 2. The alternative is to truncate it to a common 0.88 Ah basis, losing nothing but changing every cycle life in that batch. |
| **D3** | Do the 5 continued cells enter as joined records, as first-segments-only, or get excluded? | Issue 3. The join introduces a protocol-change artefact of up to 0.01 Ah. |
| **D4** | Are censored cells dropped, or kept with a censoring indicator? | Issue 4. Dropping them biases the cycle-life distribution downward; keeping them requires the downstream method to handle censoring. |
| **D5** | Do we adopt upstream's published cell selection (the paper's 124) or our own? | Issue 14. Three of upstream's six 2018-04-12 removals have no stated justification and look healthy. |

---

## 1. `cycle_life` in the struct is not a cycle life

**What and who.** All 46 cells of 2017-05-12 and 44 of 46 in 2018-04-12 (the other two
are `NaN`). For those, `cycle_life == n_cycles + 1` exactly.

**Evidence.** `schema.md`; `cell_inventory.csv:cycle_life_struct_field`. The paper's own
`LoadData.m` computes `find(QDischarge < 0.88, 1)` and falls back to
`size(cycles,2) + 1` when that never fires. It never fires for those two batches,
because they *stop at* 0.88 Ah rather than crossing it: their last recorded capacity is
0.8800–0.8834 Ah. Only 2017-06-30 was cycled past the threshold, which is why its
`cycle_life` is 20–37 cycles *below* its record length. Agrees with no page — the pages
never describe this field.

**Options.**
- *Use the struct field as-is.* Zero work; silently wrong for 90 of 135 cells, where it
  is just the record length.
- *Recompute as the first cycle below 0.88 Ah.* Faithful to the paper's definition, but
  returns nothing for 2017-05-12 and 2018-04-12, censoring 87 cells that plainly ran to
  completion.
- *Recompute with an explicit basis per cell* — the strict crossing where one exists,
  the last recorded cycle where the test terminated at criterion, and nothing where the
  cell is censored.

**Recommendation.** The third. Already implemented as
`cell_inventory.csv:cycle_life_cycles` with `cycle_life_basis` recording which rule
applied per cell. Never use `cycle_life_struct_field` for anything.

**Decision needed:** D1 — whether `test_terminated_at_criterion` counts as a measured
cycle life. I think yes: those cells are within one cycle of the threshold, so the
error is ≤1 cycle on values of 500–2200.

---

## 2. The three batches do not share an end-of-life criterion

**What and who.** All 48 cells of 2017-06-30. That batch was cycled to **75% of
nominal (0.825 Ah)**; the other two stopped at **80% (0.88 Ah)**.

**Evidence.** `tables/eol_criterion.csv`, `fig01`. Median last capacity: 0.8807 Ah
(80.07% of the 1.1 Ah nominal), **0.8262 Ah (75.11%)**, 0.8804 Ah (80.04%). The
2017-06-30 page says "We cycle to 75% of nominal capacity (0.88 Ah)" — two
contradictory figures in one sentence. **The data says the percentage is right and the
Ah value is wrong.** This is a direct contradiction of the parenthetical, and it means
cycle lives are not comparable across batches without adjustment.

**Options.**
- *Ignore it.* Every 2017-06-30 cycle life is inflated by the 20–37 cycles the cells
  ran between 0.88 and 0.825 Ah. In `fig08` this shows as that batch sitting on a
  visibly separate level.
- *Truncate 2017-06-30 to the 0.88 Ah crossing*, which is directly measurable there
  (`eol_cycle_strict_lt`). Puts all three batches on one basis and discards only the
  tail cycles past the threshold.
- *Keep both and always carry a batch term.*

**Recommendation.** Truncate for any cross-batch cycle-life comparison, and keep the
batch term regardless — the batches differ in rest scheme and CV cutoff too (issue 11),
so a batch effect exists independently of this.

**Decision needed:** D2.

---

## 3. The five continued cells, and the step at the junction

**What and who.** `EL150800460514, EL150800460486, EL150800460623, EL150800464977,
EL150800464865` — channels 1, 2, 3, 5, 6 in **both** batches. 140 struct rows, 135
physical cells.

**Evidence.** Case-insensitive barcode join gives exactly these five
(`cell_inventory.csv`, `fig02`). Confirms the pages. Note the barcode case differs
between files (`REPORT.md` §3) and 2017-06-30's struct rows are not ordered by channel, so
upstream's index-based `b2c7, b2c8, b2c9, b2c15, b2c16` refer to these same cells
despite looking like different channels.

**The pause was short.** The two batch dates are 49 days apart and these cells cycled
for ~44–45 of them, implying a gap of roughly **4–6 days**, consistent across all five
(4.0–4.6 days on the simplest estimate). This is approximate — it assumes `batch_date`
is the test start date and uses each cell's cycle-100 duration, which overstates
cycling time slightly because cycles shorten with age. It matters because a few days of
calendar rest is not a meaningful calendar-ageing confound, whereas months would be.

**But:** the 2017-05-12 page says the pause "lead to a rise in capacity upon
resuming". **All five drop** instead: −0.0033, −0.0093, −0.0093, −0.0028, −0.0100 Ah.
For ch 2, 3 and 6 that is 8–18× the cell's own fade over ten cycles, so it is a real
discontinuity (`tables/continuation_junction.csv`, `fig02` bottom row). A plausible but
unproven cause: the resumed cells ran under 2017-06-30's 5-minute rests instead of
2017-05-12's 1-minute rest, and more relaxation before discharge would lower measured
capacity slightly.

**Options.**
- *Join and ignore the step* (what upstream does). Introduces a ≤0.01 Ah artefact
  mid-record; harmless for cycle life, potentially significant for anything reading the
  capacity trajectory's shape.
- *Join and flag the junction cycle* so downstream code can exclude a window around it.
- *Use only the first segment* and treat the cells as censored at the pause. Loses
  1851–2236-cycle records, the longest-lived cells in the dataset.
- *Exclude the five cells.* Cleanest, costs 5 of 135 cells and the entire
  3.6C(80%) and 4C(80%) policy coverage in 2017-05-12.

**Recommendation.** Join, and record the junction cycle index per cell so a window can
be excluded when the trajectory shape matters. Do not drop them — they are the only
cells covering those two policies at that batch's conditions.

**Decision needed:** D3.

---

## 4. Seven censored cells

**What and who.** 2017-05-12 ch 13, 19, 21, 22, 31 (last capacity 0.913–0.969 Ah) and
2018-04-12 ch 33, 41 (0.937, 0.974 Ah).

**Evidence.** `cell_inventory.csv:censored`, `fig01`, `fig03`. Exactly the channels the
two pages name. The separation is unambiguous: cells that terminated at criterion end
at 0.8800–0.8834 Ah, these end at 0.9131 Ah and above, with nothing in between.

**The two batches were censored by different mechanisms**, which bears on how much
dropping them would hurt:

- *2017-05-12* — the five stop at cycles 878, 890, 896, 901, 905 (spread 27) on four
  similar 5.4C/6C policies, and they are **not** the batch's longest-running cells
  (uncensored lives run to 2236). A tight cluster across similar policies is what a
  single administrative stop looks like. Still mildly informative: all five were above
  the batch median of 841 when stopped.
- *2018-04-12* — the two stop at 2189 and 2237, and they **are** the two
  longest-running cells in that batch (next highest is 1934). This looks like cells
  stopped *because* they were outlasting the batch, which is informative censoring:
  dropping them truncates the top of the cycle-life distribution directly.

**Options.**
- *Drop them.* What upstream's Python notebook does. Biases the cycle-life distribution
  downward, and more so for the 2018-04-12 pair, which sit at the top of their batch.
- *Keep with a censoring flag*, cycle life recorded as a lower bound (their last
  recorded cycle).
- *Impute a cycle life.* Not defensible — 2018-04-12 ch 41 was still at 0.974 Ah after
  2237 cycles, so any extrapolation is a guess.

**Recommendation.** Keep and flag. Already in the inventory as `censored` with the
lower bound in `n_cycles_recorded`. Note upstream's MATLAB script calls the
2017-05-12 removal explicitly *optional* while the Python notebook presents it as
unconditional (`REPORT.md` U10, and issue 14 below).

**Decision needed:** D4.

---

## 5. 2017-05-12's cycle 1 is a zero placeholder

**What and who.** All 46 cells of 2017-05-12, cycle index 0 only.

**Evidence.** `schema.md`, `tables/cycle_indexing.csv`. All nine within-cycle arrays
are a 2-element vector of zeros, and `summary["QDischarge"][0]` is exactly 0.0. Agrees
with the page's "cycle 1 data is not available", but the mechanism matters: the row is
*retained*, not deleted, so **cycle numbering is not offset between batches** (confirmed
independently in `fig07`, where the dQ/dV peaks align across all three). A naive scan
for "first cycle below 0.88 Ah" returns cycle 1 for all 46 cells.

**Options.** Drop the row; keep it and mask the value; keep it as-is.

**Recommendation.** Keep the row (so cycle numbers stay meaningful) and mask index 0
as missing for 2017-05-12 only. Every helper in `exploration/` already skips it via
`inventory.first_valid_index`, and the count is recorded per cell as
`n_leading_invalid_cycles`.

**No decision needed.**

---

## 6. Four computer restarts, and the cycles they corrupt

**What and who.**

| batch | event | cycles | gap | cells with direct evidence |
|---|---|---|---|---|
| 2017-05-12 | 1 | 13 | 6.98–7.00 h | ch 7, 15, 16 (+11 cells with IR = 0) |
| 2017-05-12 | 2 | 879–902 | 4.64–4.68 h | ch 5, 44, 25 (+8 cells with IR = 0) |
| 2017-06-30 | main | 246–258 | 8.19–8.47 h | 7 cells mid-charge, 15 with capacity artifacts |
| 2017-06-30 | third (**undocumented**) | 311–331 | not sized | ch 1, 2, 3 via IR = 0; ch 3's capacity dip |
| 2017-06-30 | near-EOL | 1000 | 21.51 h | ch 3 (EL150800460623) alone |

**Evidence.** `tables/time_gaps.csv`, `tables/ir_zero_cycles.csv`,
`tables/capacity_spikes.csv`, `fig06`, `fig04`. The structs carry no wall clock, but
`chargetime` inflates from ~10 min to 490–1290 min when a restart interrupts a charge,
which sizes the gap directly. The 2017-06-30 main event is confirmed as a *single*
wall-clock interruption: the cycle at which each cell shows its artifact is
anti-correlated with that cell's cycle duration at **r = −0.993**, placing the event at
247–253 hours into the batch for every affected cell.

Two corrections to the pages: the page says "spikes" in capacity, but **12 of the 14
artifacts near cycle 250 are downward dips** (−0.02 to −0.14 Ah); and the near-EOL ch 3
event is a 21.5 h gap with only a −0.0085 Ah capacity step, not a dramatic spike.
2018-04-12 has **no** cycle anywhere above 60 min of charge time.

**Options.**
- *Nothing.* ~25 cycles out of ~110,000 carry an artifact; they will distort any
  per-cycle feature that touches them and any smoothing window that spans them.
- *Flag the affected cycles* and let downstream code decide.
- *Mask the affected cycles* (set to missing, do not interpolate).
- *Drop the affected cells.* Disproportionate — these are single bad cycles in
  otherwise sound records.

**Recommendation.** Flag, and mask for any feature computed over a window. A specific
mask list is derivable from the three tables above; I have not generated it because
the window width depends on what you compute.

**Note:** `eda_utils.despike()` already exists and masks isolated single-cycle spikes
for plotting. It uses a 0.08 Ah threshold, which is coarser than the 0.01 Ah used here
and will miss the smaller restart dips.

---

## 7. Thermocouples: two documented, at least six more not

**What and who.** Ranked by how far a cell's temperature rise falls below what its
charging policy predicts (`tables/thermocouple_outliers.csv`, `fig05` bottom right):

| cell | residual | T_rise | on a page? |
|---|---|---|---|
| 2017-05-12 ch 36 | **−5.32 °C** | 0.71 °C | **no** |
| 2018-04-12 ch 39 | −4.40 °C | 0.82 °C | **no** |
| 2017-06-30 ch 7 | −4.27 °C | 2.31 °C | yes — "fallen off" |
| 2017-05-12 ch 5 | −3.93 °C | 1.28 °C | **no** |
| 2017-06-30 ch 4 | −3.43 °C | 3.15 °C | **no** |
| 2018-04-12 ch 14 | −3.39 °C | 1.81 °C | **no** |
| 2017-06-30 ch 21 | −0.53 °C (39th of 140) | 6.04 °C | yes — "fallen off"; **ordinary on this metric, but see the late-life column below** |

**Evidence.** The discriminant is median(Tmax − Tmin) against a per-batch fit on
`heat_proxy = C1·Q1 + C2·(80−Q1)`, the relative I²R heat over the fast-charge portion.
ch 7 is confirmed emphatically — 2.31 °C rise against 5.65 °C for ch 8 on the
*identical* policy — and its rise falls 0.63 °C from early to late life, consistent
with detaching during the test, which is how it was found only on unloading.

**ch 21 is corroborated too, but on a different column.** Its average residual is
unremarkable (−0.53 °C, 39th of 140), and reading that column alone is what first made
this claim look unsupported. It is the wrong column: a thermocouple that detaches
*part-way through* leaves a step, not a low average. On `T_rise` last-quarter minus
first-quarter, ch 21 is **4th of 140 at −2.07 °C**. The page says the detachment was
found on unloading — i.e. late — so the late-life step is precisely the signature the
claim predicts, and it is there. The average-residual table above and this late-life
measure answer different questions; a cell can fail either independently.

The 2018-04-12 page mentions no thermocouple problems, yet two of its cells are among
the worst on the residual, and its ch 15 shows the 2nd largest late-life drop in the
dataset (−7.19 °C) despite no claimed swap in that batch — recorded as an observation
only, since per-cell `Tmax − Tmin` cannot establish a channel swap.

**Options.**
- *Trust the pages only.* Leaves five bad thermocouples unflagged, including the two
  worst in the dataset (ranks 1 and 2 of 140), and misses ch 21's real signature.
- *Flag on the measured residual*, with the threshold stated (I used −3 °C).
- *Drop the affected cells.* Unjustified — their capacity data is unaffected.

**Recommendation.** Flag on **both** measures, each with its cutoff stated, because they
catch different faults: the six cells with residual below −3 °C (ranks 1–6 of 140) for
poor contact throughout, and the cells with a late-life `T_rise` drop beyond −2 °C
(ranks 1–4 of 140: 2017-06-30 ch 16, 2018-04-12 ch 15, 2017-05-12 ch 15, 2017-06-30
ch 21) for contact lost mid-test. Treat temperature as unusable for those cells and keep
every one of them for capacity work. ch 21 is flagged on its own evidence, not on the
page's word.

**Caveat on my own method:** the residual depends on the policy-heat model, which is
crude (it ignores the CV tail and the common discharge). It ranks cells sensibly and
the extreme cases are unambiguous, but a cell at −3.1 °C is not meaningfully different
from one at −2.9 °C.

---

## 8. The ch 15 / ch 16 swap cannot be settled

**What and who.** Channels 15 and 16 in 2017-05-12 and in 2017-06-30.

**Evidence.** `tables/thermocouple_swap.csv`. In 2017-05-12 both channels run the
**same** policy, 5.4C(60%)-3C, and are each other's only replicate — so no measurement
can distinguish the swapped from the unswapped assignment. In 2017-06-30 the policies
differ, and swapping fits 1.4% better (SSE 4.898 vs 4.965), which is not evidence. The
same test applied to 2018-04-12, **where no page claims a swap**, prefers the swapped
assignment far more strongly (2.50 vs 4.39). A test that fires harder on the negative
control is not usable.

**Options.** Apply the swap on the page's word; ignore it; flag the four cells'
temperature as uncertain.

**Recommendation.** Flag, don't swap. Applying a swap we cannot verify risks
introducing the very error we're trying to fix, and it only matters if you join
temperature to a specific barcode. If the analysis is policy-level and both channels
share a policy (2017-05-12), the swap is irrelevant by construction.

**Needs a decision only if** you intend per-cell thermal analysis on those four cells.

---

## 9. 2018-04-12 ch 46 is unusable for voltage-domain features

**What and who.** 2018-04-12 ch 46 (`el150800737364`).

**Evidence.** Measured as the 99th-percentile roughness of ΔQ₁₀₀₋₁₀(V) relative to that
cell's own ΔQ amplitude: ch 46 is at **0.316**, against a batch median of 0.004 and a
next-worst of 0.039 — 85× the median, 8× the runner-up. Visible directly in `fig07`
(bottom right), swinging ±0.01 Ah against a 0.008 Ah signal. It is also the only cell
in its batch with capacity artifacts (+0.063, +0.069 Ah at cycles 597–598). Confirms
the page. Upstream's `LoadData.m` removes it "upfront".

**Correction to my own Step 2 verdict:** I first called this unconfirmed because the
raw within-cycle voltage second-difference does not single ch 46 out (ch 48 matches
it). That metric is dominated by the sampling grid and was the wrong test.

**Options.** Drop the cell; keep it and exclude it from ΔQ(V) features; keep it
entirely.

**Recommendation.** Keep for capacity and cycle life, exclude from any ΔQ(V)-based
feature. Its noise is 32% of its own degradation signal, so it would act as a
high-leverage outlier in exactly the feature the paper is built on.

**Also worth flagging:** 2017-05-12 ch 43 (0.147) and 2017-06-30 ch 41 (0.186) have
comparably poor noise-to-signal and are on no page.

---

## 10. Four channels have no data; two are undocumented

**What and who.** 2017-05-12 ch 4 and 8 (documented); **2018-04-12 ch 26 and 31**
(on no page).

**Evidence.** `cell_inventory.csv` rows with `in_struct = False`. Struct row counts are
46 / 48 / 46 against a 48-channel potentiostat.

**Recommendation.** Nothing to clean — there is no data. Keep the rows in the inventory
so the channel map is complete and so the "about 48 cells per batch" statement
reconciles. Worth asking the data authors about ch 26 and 31, since an undocumented
absence might mean those tests failed in a way that affected their neighbours.

---

## 11. The batches use different protocols — do not pool without a batch term

**What and who.** All cells. Verified rather than assumed:

| parameter | 2017-05-12 | 2017-06-30 | 2018-04-12 | agrees with pages? |
|---|---|---|---|---|
| CV cutoff current | 0.0200 C (C/50) | 0.0200 C (C/50) | **0.0500 C (C/20)** | yes, exactly |
| rests | one, 55.8–60.9 s | two, 295.8 + 295.0 s | 10.1 + 4 + 4 s | yes, within sampling |
| charge time 0–80% | 8.996–13.342 min, varies by policy | ~10.0 min fixed | ~10.0 min fixed | yes |
| end-of-life | 0.88 Ah | **0.825 Ah** | 0.88 Ah | no — see issue 2 |
| baseline temperature | 30.10 °C | 30.03 °C | **31.45 °C** | not stated |
| CV share at last cycle | 0.842 | 0.863 | 0.654 | not stated |

**Evidence.** `tables/cycle_metrics_life.csv`, `tables/chargetime.csv`,
`tables/temperature.csv`, `fig09`. The 2017-06-30 "fixed at 10 minutes" applies to its
43 new cells; the 5 continued cells keep their 2017-05-12 policies at ~13.4 min.

**Recommendation.** Always carry the batch as a factor. Never randomly split cells
across batches as though they were exchangeable. The differences are real, measured and
in at least two cases (CV cutoff, end-of-life) large enough to shift any
capacity-derived feature.

---

## 12. The chamber drifts during a run

**What and who.** All batches, 2017-05-12 worst.

**Evidence.** `tables/chamber_drift.csv`, `fig05`. The batch-median Tavg wanders
**2.97 °C** over 2017-05-12 (1.98 °C for 2017-06-30, 2.58 °C for 2018-04-12), with
visible step changes at cycles ~350, ~500 and ~730. This confirms the page's
"temperature control is somewhat inconsistent" — but it is drift over *time*, affecting
all cells together. Between *cells*, 2017-05-12 is the tightest of the three
(IQR 1.45 °C), which is why my first verdict on this claim was wrong.

**Options.** Ignore; include temperature as a covariate; restrict comparisons to
within-batch.

**Recommendation.** Don't attempt to correct it — there is no chamber-setpoint record
to correct against, only cell-surface readings that confound chamber and contact
quality. Note it as a limitation and prefer within-batch comparisons.

---

## 13. Corrupted policy strings

**What and who.** Eight rows.

**Evidence.** `cell_inventory.csv:policy_truncated_in_any_segment`.
- The five continuation rows in 2017-06-30 lose their leading current: `80%)-3.6C` for
  `3.6C(80%)-3.6C`, `80%)-4C` for `4C(80%)-4C`.
- 2017-06-30 ch 28 stores `4C(31%)-5`, missing the second step's trailing `C`.
- All 46 of 2018-04-12 carry a `-newstructure` suffix, so their policies compare
  unequal to identical 2017 policies (e.g. `4.8C(80%)-4.8C` appears in both batches).

**Recommendation.** For the five continuations, take the policy from the 2017-05-12
segment, which is intact — already done. For ch 28, read `C2 = 5.0` and flag the string
as malformed (the number is intact; only the unit character is missing). Split
`-newstructure` into a separate field. All three are implemented in
`matr.parse_policy`; none involves inventing a value.

**No decision needed**, but note this is the one place I am *parsing around* a
corruption rather than just flagging it, so say if you'd rather these eight cells carry
a null policy.

---

## 14. Upstream's published cleaning does not match its own documentation

**What and who.** The paper's 124-cell selection.

**Evidence.** `Load Data.ipynb` vs `LoadData.m`. The reconciliation is exact:

```
140 struct rows − 5 continuation duplicates          = 135 physical cells
            − 5 censored in 2017-05-12               = 130
            − 6 removed from 2018-04-12              = 124  (the paper's count)
```

But of those six 2018-04-12 removals, only three are named anywhere: ch 46 (noisy) and
ch 33, 41 (censored). The other three — **ch 6, ch 7, ch 12** — terminated normally at
0.8804–0.8806 Ah and are removed under the comment "remove the noisy Batch 8 batteries",
with nothing on the 2018-04-12 page naming them.

The label is not arbitrary. Ranked by ΔQ(V) noise-to-signal, **ch 12 and ch 6 are 3rd
and 4th of 46**, behind only ch 46 and the censored ch 41. But they sit at 0.019 and
0.017 against ch 46's 0.316 — roughly 17× milder — and ch 7 ranks 11th, squarely
unremarkable. So upstream drew a noise threshold somewhere between rank 4 and rank 5
that it never documented and that the pages do not support. The two scripts also
disagree on method: the MATLAB version removes ch 46 "upfront", then applies a
`QDischarge(end) > 0.885` censoring filter, then drops `nind = [3, 40:41]`; and it calls
the five-cell 2017-05-12 removal **optional**, which the Python notebook presents as
unconditional.

**Options.**
- *Adopt the paper's 124* for comparability with published results, accepting three
  unexplained removals.
- *Adopt our own selection* from the inventory, which is reproducible and documented
  per cell.
- *Carry both* as two columns.

**Recommendation.** Carry both: an `in_paper_124` flag alongside our own flags, so
results can be reported on either basis and the difference measured.

**Decision needed:** D5.

---

## Questions the data cannot answer

1. **Was 2017-05-12's excluded cycle 1 the initial C/10 cycle?** The slot is a zero
   placeholder, and the page's stated reason — sampling rate too high — fits a slow
   low-rate cycle. Suggestive, not provable.
2. **Where are the other C/10 cycles?** Scanning the first three and last three cycles
   of all 140 struct rows, the minimum peak current is 4.00 C — **no C/10 cycle exists
   in any struct**. 2017-06-30's claimed initial one and 2018-04-12's claimed final one
   are both absent. They presumably survive in the per-cell raw CSVs, which this copy
   of the dataset does not include. *Getting those CSVs would also answer Q1.*
3. **The IR pulse width** (30 vs 30 vs 33 ms). The within-cycle sampling interval is
   ~5 s, roughly 1700× the pulse. Not measurable, at all.
4. **Which 2018-04-12 cells had OCV errors.** The page says "some cells" without naming
   them. Inflated charge times are present (44 of 46 cells have at least one cycle over
   their own median + 3 min, worst +13.6 min) but 2017-05-12 and 2017-06-30 show the
   same or worse, so the signature is not specific and cannot identify them.
5. **Whether ch 15/16 were actually swapped** — see issue 8.
6. **Absolute dates and times for any cycle.** `t` resets every cycle and there is no
   test-time field, so gaps are only measurable when they happen to interrupt a charge.
   Any restart that struck during rest or discharge is invisible except through its
   capacity or IR signature.
7. **Why the continuation junctions step down** rather than up (issue 3). The rest-scheme
   change is a hypothesis the data is consistent with but does not establish.
8. **Why 2018-04-12 runs ~1.4 °C hotter.** Could be chamber setpoint, fixture, or
   thermocouple practice; the data cannot separate them.

---

## Summary

**Verified cell count.** 135 physical cells, from 140 struct rows (46 + 48 + 46) minus
5 continuation duplicates, across 52 channel-slots that produced no data or no cell.

| category | n | notes |
|---|---|---|
| complete | 122 | reached their test's criterion |
| censored | 7 | 2017-05-12 ch 13/19/21/22/31; 2018-04-12 ch 33/41 |
| continued | 5 | joined on barcode across two batches |
| flagged defective | 1 | 2017-06-30 ch 10, 170 cycles |
| no data | 4 channels | 2017-05-12 ch 4/8; **2018-04-12 ch 26/31 (undocumented)** |

Categories are exclusive by priority; the 5 continued and the 1 defective cell also
reached their criterion.

**Where the data departs from the transcripts.** Two claims are contradicted outright
(1 and 2); the other three are confirmed in substance but state a detail wrongly.

1. **2017-06-30's "(0.88 Ah)" is wrong** *(contradicted)* — that batch stopped at
   0.825 Ah = 75% of nominal. The "75%" is correct.
2. **No C/10 cycle exists in any struct** *(contradicted)* — neither 2017-06-30's claimed
   initial one nor 2018-04-12's claimed final one.
3. **The continuation junctions step down, not up** *(detail wrong in a confirmed
   claim)*. All five, by up to 0.0100 Ah, against a page that says capacity rose on
   resuming.
4. **The cycle-250 artifacts are mostly dips, not "spikes"** *(detail wrong in a
   confirmed claim)* — 12 of 14 are downward.
5. **2017-05-12's "inconsistent temperature" is drift over time, not spread between
   cells** *(detail wrong in a confirmed claim)* — on the between-cell measure that batch
   is the tightest of the three.

ch 21's thermocouple was listed here in an earlier draft as unsupported. It is not: the
claim holds on the late-life step (4th of 140 at −2.07 °C), which is the signature a
detachment "found on unloading" predicts. Only the average residual is ordinary.

**Unexpected, on no page.**

1. **2018-04-12 is missing channels 26 and 31** entirely.
2. **A third 2017-06-30 interruption** at ~272 h, visible only through `IR = 0` on
   ch 1/2/3 and ch 3's capacity dip at cycle 311.
3. **All 22 `IR = 0` readings sit on a restart** — a second, independent restart
   detector, and the one that found finding 2 above.
4. **Five of the six worst thermocouple signatures belong to cells no page mentions** —
   ranks 1, 2, 4, 5 and 6 of 140 by charge-heat residual, with only rank 3 documented
   (ch 7). The two worst in the dataset are undocumented: 2017-05-12 ch 36 (0.71 °C rise)
   and 2018-04-12 ch 39 (0.82 °C). The 2018-04-12 page mentions no thermal problems at
   all, yet supplies two of the five. Stated as ranks because no physical cutoff
   separates a loose thermocouple from a cool-running cell.
   Separately, the three largest **late-life** `T_rise` drops are 2017-06-30 ch 16
   (−8.00 °C), 2018-04-12 ch 15 (−7.19 °C) and 2017-05-12 ch 15 (−6.26 °C) — the 15/16
   channels the 2017 pages call swapped, plus one in a batch claiming no thermal issue.
   Observation only; a per-cell metric cannot establish a swap.
5. **Cell EL150800460514 (ch 1 in both batches) is chronically glitchy** — 58 artifact
   cycles spread over cycles 12–851 in its first segment, then paired dip/recover events
   every ~10 cycles in its second.
6. **2017-05-12 ch 17 records 2.884 Ah at cycle 40** — 2.62× nominal, against neighbours
   of 1.0695 Ah, and the largest capacity value anywhere in the dataset.
7. **Baseline temperature differs between batches (~1.4 °C) by more than it varies
   within one**, against a 30 °C setpoint.
8. **2017-06-30 ch 4, 7 and 8 spend 41–46% of their cycles with an inflated charge
   time**, against a batch median of 53 cycles; ch 4 and ch 7 are also that batch's two
   worst thermal-contact cells.
9. **Upstream drops three 2018-04-12 cells** (ch 6, 7, 12) with no page justification,
   on an undocumented noise threshold: ch 12 and ch 6 do rank 3rd and 4th of 46 on
   ΔQ(V) noise, but ~17× milder than ch 46, and ch 7 ranks 11th. Its MATLAB and Python
   scripts also disagree on method and on whether the 2017-05-12 removal is optional.
10. **Barcode case is inconsistent between files**, and 2017-06-30's struct rows are not
    ordered by channel — both are traps for an index-based or case-sensitive join.
11. **Eight policy strings are corrupted in storage**, five of them silently losing
    their leading charge rate.

**Two corrections to my own earlier reporting**, both from building the figures:
ch 46's noise *is* real and confirms the page (I first used a metric that could not see
it), and the CV share at the last cycle is 0.842 / 0.863 / 0.654, not the
0.63 / 0.81 / 0.64 I reported at the Step 2 checkpoint — that calculation keyed the CV
window to each cycle's own maximum voltage and returned a spurious zero on 13 cells.
