# The independent audit vs. two external repositories

Compares the data this repository's audit produced (`REPORT.md`,
`analysis_set_cells.csv`, `analysis_set_cycles.csv`) against the data actually used by:

- **Repo A** — <https://git.rwth-aachen.de/isea/battery-degradation-trajectory-prediction>
  (ISEA, RWTH Aachen; GitHub mirror `isea-rwth-aachen/battery-degradation-trajectory-prediction`;
  paper: Li et al., *Forecasting battery capacity and power degradation with multi-task
  learning*, [arXiv:2111.14937](https://arxiv.org/abs/2111.14937))
- **Repo B** — <https://github.com/arslimane/Energetic-project-2>
  (Arbaoui, Samet, Ayadi, Mesbahi, Boné, *Dual-Model Approach for One-Shot Lithium-ion
  Battery State of Health Sequence Prediction*, ARRAY 2024)

Everything below about Repo B was re-derived from the three raw `.mat` files in `Data/`
by running Repo B's own published code path against them. Scripts used are listed in §8.

---

## 1. Headline

**Repo A does not use this dataset at all.** It is ISEA's own ageing campaign — a
**different cell format** (~1.83 Ah initial capacity, against MATR's 1.1 Ah nominal),
cycled far deeper (down to ~46% SOH, against MATR's ~80%), distributed as
`Degradation_Prediction_Dataset_ISEA.mat` plus a raw-data DOI
(`10.18154/RWTH-2021-04545`). There is **zero cell overlap** with the MATR/Severson
data, so nothing in the audit's findings transfers to it and none of its numbers
contradict ours. The comparison with Repo A is therefore **methodological only**.

**Repo B uses exactly the same three files we do** — the same
`2017-05-12`, `2017-06-30` and `2018-04-12` `batchdata_updated_struct_errorcorrect.mat`
downloads, loaded by code with the same lineage as this repo's `build_pkl.py`.
It is a direct, cell-for-cell comparison, and it is where all the substantive
divergence lies.

The largest divergence is the one `REPORT.md` §5 anticipates: "80% SOH" has two
readings, and the per-cell-initial reading leaves only 43 usable cells. **Repo B uses
the per-cell-initial reading.** Under that definition **96 of its 139 cells never reach
end of life**, and two of the three batches contain no end-of-life event at all. Its
abstract describes SOH estimation "up to the End Of Life (EOL)"; on these three files
that holds for the 2017-06-30 batch only.

---

## 2. What each project's data actually is

| | this repo (audit) | Repo A — RWTH ISEA | Repo B — Energetic-project-2 |
|---|---|---|---|
| dataset | MATR / Severson et al. 2019 | ISEA's own ageing campaign | MATR / Severson et al. 2019 |
| raw source | 3 `.mat` batch structs | `Degradation_Prediction_Dataset_ISEA.mat` + raw DOI | the **same 3** `.mat` batch structs |
| cells | **135** physical | **47** (README says 48) | **139** struct rows |
| cell overlap with ours | — | **none** | **complete** |
| cell | A123 APR18650M1A LFP/graphite, 1.1 Ah nominal | not MATR; ~1.83 Ah initial | same as ours |
| depth of cycling | to ~80% of nominal | to **~46%** of initial | to ~80% of nominal |
| cycle lives | 148 – 2236 | 1460 – 1840 | 148 – 2236 |
| target quantity | cycle at which 0.88 Ah is crossed | future **capacity in Ah** | **SOH ratio** `QD/QD[1]` |
| EOL definition | 0.88 Ah = 80% of **nominal** | none needed (no threshold) | SOH < 0.80 of **own initial** |
| cleaning | audited, decided, flagged in place | not documented | **none** |
| train/test split | `in_paper_124` carried; batch kept as a factor | 5 **named** cells held out | unseeded `random.shuffle`, 60/40 |
| modelling code public | no (upstream academic licence) | no (academic licence) | yes |

---

## 3. Repo A (RWTH ISEA) — a different dataset, so compare the method

Repo A ships only its preprocessing stage; the modelling code is behind an academic
licence, the same situation as this repo's upstream. What is public:

`Degradation_Prediction_Dataset_ISEA.mat` holds a MATLAB struct `TDS` already cut into
growing-window samples. Read directly, it contains:

```
TDS rows (samples)      10,686
distinct cells               47        (contiguous 1..47; the README says 48)
samples per cell            192 - 268  (median 223)
History length               21 - 288  entries, 5-cycle spacing
Target length                 9 -  39  entries, 50-cycle spacing
initial capacity         1.8276 - 1.8491 Ah
final capacity           0.8501 - 0.8566 Ah
final SOH vs own initial  0.461 - 0.468
longest cycle reached      1460 - 1840
```

**This is the decisive contrast with Repo B.** All 47 ISEA cells are cycled to ~46% of
their own initial capacity, so **every one of them crosses 80%-of-initial** — 47 of 47.
The MATR cells stop at ~80% of *nominal*, which is only ~82% of their own initial
capacity, so only 43 of them ever cross 80%-of-initial (`REPORT.md` §5). The
per-cell-initial SOH definition is therefore workable on ISEA's data and leaves
**43 of 135** labelled cells on ours. The definition is not wrong in itself; what it
yields depends on how deep the cells were cycled. ISEA's are cycled deep enough for it;
these three files are not (§4.5).

Two further observations. ISEA's cycle lives span 1460–1840 cycles against MATR's
148–2236 — a far narrower target distribution.
And the struct's field is spelled `Target_expanded`, while the README documents
`Target_Expanded` — the preprocessing script reads it by position
(`data.iloc[row, -1]`) so it is unaffected, but code written from the README will fail.

**Three method choices that differ from Repo B's:**

1. **The target is capacity in Ah, not a normalised SOH.** There is no denominator, so
   the entire trap in `REPORT.md` §5 cannot arise. This is worth noting as a design
   option: our audit resolved the denominator question (D0 → nominal); Repo A dissolves it.
2. **The test split is by named cell.** `Preprocessing_dataset.m` sets
   `test_cells = [15,20,25,30,35]` and routes whole cells to test. The split is
   cell-disjoint by construction and reproducible by inspection — no cell can appear on
   both sides. All five are present in `TDS`, and they carry 1083 of the 10,686 samples
   (10.1% of samples, 5 of 47 cells). Compare Repo B's unseeded shuffle (§4.3).
3. **Padding is explicit and the mask value is documented**, with the padding buffer a
   user choice rather than a hard-coded 2000.

**Four points to record about the published pipeline:**

1. **The train/validation split leaks cells.**
   `Generating_features_labels_and_training_testing_split.py` does
   `tts(X_Data, y_Data, test_size=0.15, shuffle=True)` over **growing-window samples**,
   not cells. Since every cell contributes many samples, validation rows share cells with
   training rows. The *test* set is clean; the validation estimate is not, so it will
   read optimistically and is a poor early-stopping signal.
2. **Nothing is seeded.** `np.random.permutation` in `array_shuffler` and the
   `train_test_split` call both run without a seed, so neither the shuffle nor the
   train/val split is reproducible between runs.
3. **A filename mismatch blocks a clean run.** `Preprocessing_dataset.m` loads
   `Lifetime_Prediction_Dataset_ISEA.mat`; the repository ships
   `Degradation_Prediction_Dataset_ISEA.mat`. The README also refers to
   `Preprocessing_MATLAB_dataset.m`, while the file is named `Preprocessing_dataset.m`.
4. **The noise augmentation is multiplicative, not additive.** The code is described as
   additive white Gaussian noise, but computes `nval2 = val2*r2; History = val2 + nval2`,
   i.e. noise **scaled by the signal** — multiplicative, so its absolute magnitude
   shrinks as the cell fades. With `sigma = 0.005` the effect is small, but a reader
   reproducing "AWGN, sigma=0.005" will not reproduce this.

**No data-quality audit is published for Repo A's 47 cells.** There is no equivalent of
`step2_findings.md` — no statement of censored cells, channel dropouts, restarts or
sensor faults. That is not a contradiction of our findings, but it does mean the audit
this repo performed has no counterpart there to compare against.

---

## 4. Repo B — the same data, so compare the numbers

### 4.1 The loader is this repo's loader

`Generating pickle files.ipynb` is the upstream `BuildPkl_Batch*.ipynb` notebook with
`.value` replaced by `[()]` — the same one-line fix, for the same reason, that any
working port of those notebooks needs under h5py 3.x. It produces the same nested-dict
shape and, like the upstream notebooks, **captures neither `barcode` nor
`channel_id`**.

That omission is the root of §4.2 and §4.3 below: without `barcode` there is no way to
notice that five of the cells are the same physical cell twice. `matr.decode_mcos_string`
exists in this repo precisely to recover those fields.

### 4.2 Cell selection: 139 vs our 135 vs the paper's 124

Repo B keeps all 140 struct rows, then drops one with `cells = cells[1:]`, giving the
139 its notebook prints. The official recipe in `Load Data.ipynb`
(and `eda_utils.load_clean_dataset`) deletes 11 rows outright (5 from batch 1, 6 from
batch 3) and merges a further 5 batch-2 rows into their batch-1 counterparts, so
140 − 11 − 5 = **124**.

| | rows |
|---|---|
| struct rows in the three files | 140 |
| Repo B's modelled set | **139** |
| this repo's physical cells | **135** |
| this repo's default trajectory set (`use_for_trajectory`) | **130** (123 of which are labelled) |
| the paper's published count | **124** |

Repo B therefore retains **16 struct rows that the official recipe removes or merges**:

| rows retained | what they are | audit reference |
|---|---|---|
| `b1c8 b1c10 b1c12 b1c13 b1c22` | the 5 censored 2017-05-12 cells — they never reached end of life | `REPORT.md` §3, D4 |
| `b2c7 b2c8 b2c9 b2c15 b2c16` | the batch-2 halves of 5 cells that are **already counted** in batch 1 | §4.3 below, D3 |
| `b3c2 b3c23 b3c32 b3c37 b3c42 b3c43` | the 6 noisy / censored 2018-04-12 channels (incl. the censored ch 33, ch 41) | U10, D5 |

That is 5 + 5 + 6 = **16**, not the 15 that 139 − 124 suggests, because Repo B also
drops one row the official recipe *keeps*. The counts reconcile exactly:
124 + 16 − 1 = **139**.

**The one row it drops is a consequential one.** `cells[1:]` removes `b1c0`, which is
`EL150800460514`, 2017-05-12 ch 1 — simultaneously (a) the cell finding **U5** singles
out as chronically glitchy, and (b) one of the five continuation cells. But it keeps
`b2c7`, the *second half of that same physical cell*, whose glitching U5 also records.
So the drop removes half of the worst cell and leaves the other half in.

### 4.3 Five physical cells enter the model twice

Joining on the barcode Repo B's loader discards:

| barcode | 1st segment | 2nd segment |
|---|---|---|
| `el150800460514` | `b1c0` (1188 cy) | `b2c7` (661 cy) |
| `el150800460486` | `b1c1` (1177 cy) | `b2c8` (980 cy) |
| `el150800460623` | `b1c2` (1175 cy) | `b2c9` (1059 cy) |
| `el150800464977` | `b1c3` (1224 cy) | `b2c15` (207 cy) |
| `el150800464865` | `b1c4` (1225 cy) | `b2c16` (481 cy) |

Two consequences:

1. **Train/test leakage.** Repo B shuffles the cell list and splits 60/40. Four of these
   five pairs survive the `cells[1:]` drop, so a shuffle can put one half of a physical
   cell in train and the other half in test. The halves share a cell, a channel, a
   fixture and a charge policy, so a test score computed on them is optimistic.
   This is exactly what decision **D3** joins on barcode to prevent.
2. **The label on the second segment is wrong** — see next.

### 4.4 SOH normalised to an already-aged capacity

Repo B sets `initial_Qd = cell['summary']['QD'][1]` and `SOH = QD/initial_Qd`. For the
five second segments, `QD[1]` is the capacity of a cell that has **already run
~1200 cycles**, so its SOH is reset to 1.0 when the cell is in fact well degraded:

| barcode | true BoL (Ah) | Repo B denominator (Ah) | true SOH at seg-2 start | Repo B's value | final SOH: Repo B vs true |
|---|---|---|---|---|---|
| `el150800460514` | 1.0707 | 1.0233 | 0.956 | 1.000 | 0.863 vs 0.825 |
| `el150800460486` | 1.0753 | 1.0265 | 0.955 | 1.000 | 0.857 vs 0.818 |
| `el150800460623` | 1.0799 | 1.0317 | 0.955 | 1.000 | 0.854 vs 0.816 |
| `el150800464977` | 1.0797 | **0.9717** | **0.900** | 1.000 | 0.906 vs 0.815 |
| `el150800464865` | 1.0784 | 1.0096 | 0.936 | 1.000 | 0.872 vs 0.816 |

SOH is overstated by **4.4–10.0 percentage points** at the start of the second segment
and **3.8–9.1 pp** at the end. SOH is Repo B's *target*, so this is an error in the
label, not in a feature — and against a label whose whole range is 1.00 → 0.80 (20 pp),
a 9 pp error is nearly half the dynamic range.

### 4.5 The denominator choice, and what it costs

This is the central divergence. `REPORT.md` §5 sets it out as a decision (**D0**) and
takes nominal; Repo B takes per-cell-initial. The choice is not stated in any of the
three Repo B files read for this comparison (§8), nor are its consequences for the
cell count.

| "80% SOH" means | threshold | cells with a usable trajectory | cells observed to reach it |
|---|---|---|---|
| 80% of **nominal** 1.1 Ah — this repo | 0.88 Ah | 135 of 135 | **128 of 135** (43 measured crossings + 85 terminated at criterion; 7 censored) |
| 80% of each cell's **own initial** — Repo B | ~0.85 Ah | 139 of 139 | **43 of 139** |

(The denominators differ because Repo B works from the 139 inventory rows rather than the
135 joined physical cells. The "usable trajectory" and "reaches the threshold" columns are
distinct questions — see `REPORT.md` §5.)

Measured from the raw files under Repo B's own formula:

```
cells reaching SOH < 0.80 :  43 of 139
never reaching it         :  96 of 139

by batch:            reaches EOL / rows
  2017-05-12                0 / 45
  2017-06-30               43 / 48
  2018-04-12                0 / 46

final SOH (their definition), median by batch:
  2017-05-12   0.819     (min 0.805)
  2017-06-30   0.771     (min 0.763)
  2018-04-12   0.827     (min 0.820)
```

So **two of the three batches contain no end-of-life event at all** under Repo B's
definition, and the paper's claim of SOH prediction "up to the End Of Life" is supported
only by the 2017-06-30 batch. The audit chose nominal for this reason: under
nominal, all 135 cells carry a trajectory and 128 carry a crossing label.

**An exact cross-check between the two analyses.** Our audit reports 43 of 135 cells
reaching 80%-of-own-initial. Repo B's data gives 43 of 139. These are the **same 43
physical cells** — every one in 2017-06-30 — reached by two independent routes:

- our 135 contains exactly 43 non-continuation 2017-06-30 cells;
- of Repo B's 48 rows for that batch, the 5 that fail to reach SOH 0.80 are *precisely*
  the 5 continuation second-segments (verified: the failing set is exactly
  `{b2c7, b2c8, b2c9, b2c15, b2c16}`), and they fail **only because** their denominator
  is an already-aged capacity.

The audit's §5 number is therefore independently corroborated, and the mechanism by
which Repo B's denominator disqualifies the five continuations is pinned down exactly.

### 4.6 Smoothing instead of flagging

Repo B applies `savgol_filter(SOH, 90, 2)` to every cell — a 90-cycle quadratic
smoother over the target. The audit's opposite choice is deliberate: known-bad cycles are
**flagged in place** (`is_measured_cycle`, `is_artifact_cycle`, `is_restart_cycle`,
`is_junction_cycle`, plus the derived `is_clean_cycle`) and `eda_utils.despike` is
documented as *plotting only*.

Measured effect, isolating the artifacts by comparing `savgol(raw)` against
`savgol(despiked)`:

| cell | artifacts | max displacement of the smoothed SOH | cycles moved >0.5 pp |
|---|---|---|---|
| `b1c18` (2017-05-12 ch 17) | 1 | **4.1 pp** | 75 |
| `b1c0` (2017-05-12 ch 1) | 2 | 2.5 pp | 34 |
| `b2c44` (2017-06-30 ch 45) | 1 | 1.1 pp | 58 |
| `b2c12` (2017-06-30 ch 28) | 1 | 1.1 pp | 58 |

17 of 140 cells carry at least one artifact detectable at a 0.03 Ah deviation from a
5-cycle running median (a threshold chosen for this check, tighter than
`eda_utils.despike`'s 0.08); **4 are materially affected** (>1 pp).

> **This is not the detector behind `is_artifact_cycle`.** That flag uses a finer
> **0.01 Ah deviation from a centred 11-cycle median** and marks 83 cycles across 22 of
> the 135 physical cells (`REPORT.md` §4.3.1). The coarser rule is used here on purpose,
> to count only artifacts large enough for a 90-cycle Savitzky–Golay filter to smear
> noticeably. The two counts answer different questions and must not be quoted
> interchangeably.

The worst, `b1c18` — **struct index 18, which is channel 17**, barcode
`EL150800453240` — has a single impossible 2.88 Ah reading at cycle 40 smeared
across 75 cycles of the target at up to 4.1 pp — about a fifth of the label's full range.
This is a bounded problem, not a pervasive one, but it is worth noting that smoothing
*spreads* a bad cycle where flagging would have removed it. No cell is shorter than the
90-cycle window (the shortest record is 169 cycles), so the filter at least never fails.

### 4.7 Within-cycle series truncated at 1000 samples, unevenly

Repo B pads/truncates every within-cycle `I`, `V`, `T` series to exactly 1000 points
(`size = min(1000, len(...))`). Because cycle duration varies by batch and grows with
age, the information discarded is **batch-dependent and age-dependent**. Probing three
points in each of the 140 cells' lives (420 cycles):

mean % of each cycle's samples discarded:

| batch | early | mid | late |
|---|---|---|---|
| 2017-05-12 | 7.8 | 6.2 | 1.2 |
| **2017-06-30** | **17.3** | **19.6** | **30.0** |
| 2018-04-12 | 0.4 | 0.0 | 0.0 |

% of probed cycles truncated at all:

| batch | early | mid | late |
|---|---|---|---|
| 2017-05-12 | 100 | 100 | 43 |
| 2017-06-30 | 98 | 96 | 90 |
| 2018-04-12 | 2 | 0 | 0 |

Overall 59% of probed cycles lose data, averaging 9.4% of the series.

Two things follow. First, this interacts badly with `REPORT.md` §8's observation that
**the CV tail grows with age** (0.315–0.330 of the charge step at cycle 10 → 0.654–0.863
at the last cycle): the truncation cuts the end of the cycle, which is exactly the part
that grows. Second, **the batch that loses the most is 2017-06-30** — the only batch that
carries any end-of-life label at all under Repo B's definition (§4.5). The cells doing
all the work for the target are the ones most heavily truncated, worsening with age.

### 4.8 What Repo B does not use

- **No `Qdlin`, `Tdlin` or `discharge_dQdV`.** Features are the raw `I`, `V`, `T`
  traces only. None of the voltage-domain ΔQ(V) features the Severson paper is built on
  are used.
- **The official splits are discarded.** `eda_utils.official_splits`' train /
  primary-test / secondary-test partition is replaced by an unseeded `random.shuffle`
  and a 60/40 cut (the code comments "to be changed to 80%"). The batches are therefore
  mixed randomly, against `REPORT.md` §8's finding that they are not exchangeable —
  target medians 841 / 481 / 1004 cycles, different CV cutoffs (C/50 vs C/20), different
  rest schemes, and a ~1.4 °C baseline offset in 2018-04-12.
- **Cycle index 0 is dropped from every cell** (`for j in range(1, num_cycle)`). For
  2017-05-12 that is correct — our inventory records `n_leading_invalid_cycles = 1` for
  all 46 of its cells, the excluded placeholder. For the other two batches cycle 0 is
  genuine, so it discards a real cycle and makes the SOH denominator the *second* cycle
  there and the *first valid* cycle in batch 1 — an inconsistency between batches.

One thing checked and found **not** to be a problem: `len(summary['cycle'])` equals the
number of cycle groups for all 140 rows, so Repo B's loop bound never over-runs.

---

## 5. Net assessment

**Against Repo A** there is nothing to reconcile — different cells, different chemistry,
different file. Its method is a useful contrast on two points: predicting capacity in Ah
sidesteps the SOH-denominator question entirely, and holding out *named* cells is a
cleaner split than anything either this repo or Repo B currently does. Its own
points to record are a cell-leaking validation split, no seeds, and a filename mismatch
that stops the published pipeline running as shipped.

**Against Repo B** the audit holds up on every point where the two can be compared. The
table pairs each audit finding with how Repo B's published pipeline handles the same
issue:

| audit finding | how Repo B is affected |
|---|---|
| D3 — join the 5 continuations | not done; 5 physical cells enter twice, enabling train/test leakage |
| D0/§5 — the SOH denominator | takes the per-cell reading; 96 of 139 cells never reach EOL |
| U5 — `EL150800460514` is chronically glitchy | half dropped by accident, half retained |
| D4 — censored cells need a flag | all 7 retained as if complete |
| D5 — the 6 noisy 2018-04-12 channels | all retained |
| §8 — the batches are not exchangeable | mixed by unseeded random shuffle |
| §8 — the CV tail grows with age | truncated away, worst in the only batch with labels |
| "flag, don't smooth" | 90-cycle Savitzky-Golay over the target instead |

One independent corroboration of the audit is worth keeping: Repo B's SOH formula
reproduces the **43-cell** figure of §5, on the same 43 cells (§4.5).

One apparent corroboration is **not** one, and is recorded here so it is not mistaken
for one later. Repo B's notebook prints a maximum of 2236 cycles, and `REPORT.md` gives
the target range as 148–2236. These are different cells. Repo B's 2236 is the record
length of `EL150800737297` (2018-04-12 ch 41) — a *censored* cell, which carries no
label in our set at all. Our 2236 is the EOL label of `EL150800460623` (2017-05-12 ch 3),
a joined continuation cell. The agreement is numerical coincidence.

Nothing found in either repository contradicts a claim in `REPORT.md`.

---

## 6. One error found in `REPORT.md` — now corrected

Unrelated to the two repositories, surfaced while cross-checking the capacity artifacts.

**U6 was wrong about the magnitude.** `REPORT.md` §4.3 read:

> U6 — **2017-05-12 ch 17 records 1.81 Ah at cycle 40**, ~1.7× nominal — physically impossible.

Measured from the file, 2017-05-12 ch 17 (`EL150800453240`, `b1c18`) records
**2.8841 Ah** at summary cycle 40 — **2.62× nominal**, with neighbours at 1.0695 Ah. No
cycle in that cell reads anywhere near 1.81 Ah. `eda_utils.despike`'s own docstring has
it right ("b1c18's QD jumps to 2.88 Ah at cycle 40"), so this looks like a transcription
slip in the report rather than a computational error. The finding itself stands, and is
stronger than stated.

**Applied.** `REPORT.md` §4.3 U6 now reads 2.884 Ah / 2.62× nominal, as do the same
finding in `step2_findings.md` (U4) and `cleaning_plan.md`. The quoted wording above is
kept verbatim so the provenance of the correction stays readable.

---

## 7. Suggested follow-ups

1. ~~**Fix U6's figure** in `REPORT.md` (1.81 → 2.884 Ah, ~1.7× → 2.62× nominal).~~ Done — see §6.
2. If the audit's analysis set is ever benchmarked against Repo B's published numbers,
   the two are **not comparable as they stand**: different cell counts (135 vs 139),
   different EOL definitions, and Repo B's test split is not reproducible. A fair
   comparison needs Repo B's pipeline re-run on `analysis_set_cells.csv`'s selection
   with a seeded, batch-aware, barcode-joined split.
3. Consider recording Repo A's framing — **capacity in Ah as the target** — in
   `cleaning_plan.md` as the option that makes decision D0 unnecessary. It is the one
   design choice either external repo makes that is cleaner than ours.

---

## 8. How this was produced

Repo B's code was read from its three published files, fetched directly:
`Generating pickle files.ipynb`, `growing window.ipynb`, `README.md`. Repo A's was read
from the GitHub mirror of the GitLab project (`README.md`, the three sub-READMEs,
`Preprocessing_dataset.m`, `Generating_features_labels_and_training_testing_split.py`)
and from `Degradation_Prediction_Dataset_ISEA.mat`.

Every number attributed to Repo B in §4 was **re-derived from this repo's own
`Data/*.mat` files** by applying Repo B's published formulas, not taken from its notebook
outputs. Its printed `len(cells) = 139` and `max cycles = 2236` are quoted from the
notebook and both reproduced independently here (on the caveat in §5 for the latter).

Scripts live in **`external_comparison/`** beside this file, with their own README:

| script | what it establishes |
|---|---|
| `final_check.py` | **re-asserts every headline number above — 27 checks, all passing.** Run this first |
| `compare_repoB.py` | Repo B's 139-cell set, its SOH denominator, the 43/139 EOL count, the 5 duplicate barcodes, censored-cell retention |
| `repoB_effects.py` | the continuation label error (§4.4), the artifact cells, a first look at truncation |
| `savgol_isolate.py` | the smoothing displacement in §4.6, by differencing `savgol(raw)` against `savgol(despiked)` |
| `trunc_scan.py` | the 420-cycle truncation scan in §4.7 |
| `check_counts.py` | that `len(summary['cycle'])` never over-runs the cycle groups |
| `inspect_isea.py` | the `TDS` struct contents for Repo A |

```bash
cd "$(git rev-parse --show-toplevel)"      # the repository root
.venv/bin/python -I exploration/external_comparison/final_check.py
```

Repo A's 18.6 MB dataset file is not vendored here; `external_comparison/README.md` gives
the one-line `curl` and the `ISEA_MAT` environment variable the two ISEA scripts read.
Without it those scripts skip; everything about Repo B runs from `Data/` alone.

The three `.mat` files were opened read-only throughout. Nothing in `Data/`,
`Data_v2/` or the existing `exploration/` files was modified. The only additions are
this file and the `external_comparison/` directory beside it.
