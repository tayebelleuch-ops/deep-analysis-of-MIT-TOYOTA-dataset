# matr_clean v0.3.1 — the window convention, measured

> **Status: planning only. Nothing in `matr_clean/` is touched by this commit.**
> Written on branch `loader-v0.3.1-plan` off `origin/main` = `1dbe475`
> (= `loader-v0.3.0^{commit}`, verified). Implementation continues on
> `loader-v0.3.1` after review.

Every figure below was **computed from the published files**, not copied from a
document: `within_cycle_index.csv` (114,738 rows, 135 cells) plus
`exploration/analysis_set_cells.csv` and `analysis_set_cycles.csv`, read
`mode="r"`. The 1..25 label-convention row was additionally re-derived by calling
the shipped `load_series` itself — see §2.3.

---

## 0. The team decisions this plan is built on

Taken as given, not re-litigated:

* Training uses **expanding / prefix windows starting at label 10**, k from 100,
  horizon 100. Label 10 is the same physical cycle in every batch.
* **Cycle 1 does not matter as an input.**
* **No prefix helper, no split logic, no filling / padding / clipping /
  interpolation anywhere.** Users load once and slice prefixes themselves.

These three decide §2's default and §3's answer, and they are the reason the
measurement that matters most in this plan is the one at `start=10` (§1.2).

---

## 1. The measured figures

### 1.1 The population, and the placeholder

| quantity | value |
|---|---|
| index rows | 114,738 |
| rows with `beyond_crossing=True` (excluded by default) | **1,179** |
| rows requestable with `beyond_crossing=False` | 113,559 |
| cells | **135** total, **108** non-test (`fold != -1`), 27 held out |
| placeholder rows in the whole index | **46** |
| distinct labels they sit on | **{1}** |
| batch they sit in | **2017-05-12** only |
| cells carrying one | **46 of 135**, of which **37 of the 108 non-test** |
| cells whose requestable labels are *not* contiguous `1..n` | **0** |
| requestable cycles per cell | min 148, median 787, max 2,237 |

So the placeholder is exactly **label 1 of each of the 46 cells of 2017-05-12**,
and there are **no interior label gaps anywhere** in the analysis set. Both facts
are load-bearing for §2.

### 1.2 Window cost: `labels` vs `measured`, both populations

`masked` = positions with `present & ~is_series_valid` (what the default mask
removes). `cells` = how many cells `drop_invalid_cells=True` would delete.
`absent` = positions with no row at all. `NaN rows` = all-NaN grid rows returned.

| start | n | labels covered | convention | population | positions | absent | masked | cells dropped | NaN rows |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 10 | 1..10 | labels | 135 | 1,350 | 0 | 56 | 47 | 46 |
| 1 | 10 | 1..10 | labels | 108 | 1,080 | 0 | 47 | 38 | 37 |
| 1 | 10 | 1..10 | measured | 135 | 1,350 | 0 | 11 | 2 | 0 |
| 1 | 10 | 1..10 | measured | 108 | 1,080 | 0 | 11 | 2 | 0 |
| 1 | 25 | 1..25 | **labels** | **135** | **3,375** | 0 | **93** | **48** | **46** |
| 1 | 25 | 1..25 | **labels** | **108** | **2,700** | 0 | **80** | **39** | **37** |
| 1 | 25 | 1..25 | **measured** | **135** | **3,375** | 0 | **48** | **18** | **0** |
| 1 | 25 | 1..25 | **measured** | **108** | **2,700** | 0 | **44** | **14** | **0** |
| 1 | 50 | 1..50 | labels | 135 | 6,750 | 0 | 118 | 48 | 46 |
| 1 | 50 | 1..50 | labels | 108 | 5,400 | 0 | 105 | 39 | 37 |
| 1 | 50 | 1..50 | measured | 135 | 6,750 | 0 | 73 | 18 | 0 |
| 1 | 50 | 1..50 | measured | 108 | 5,400 | 0 | 69 | 14 | 0 |
| 1 | 100 | 1..100 | labels | 135 | 13,500 | 0 | 126 | 48 | 46 |
| 1 | 100 | 1..100 | labels | 108 | 10,800 | 0 | 113 | 39 | 37 |
| 1 | 100 | 1..100 | measured | 135 | 13,500 | 0 | 80 | 19 | 0 |
| 1 | 100 | 1..100 | measured | 108 | 10,800 | 0 | 76 | 15 | 0 |
| **10** | **91** | **10..100** | labels | **135** | **12,285** | 0 | **71** | **19** | **0** |
| **10** | **91** | **10..100** | labels | **108** | **9,828** | 0 | **67** | **15** | **0** |
| **10** | **91** | **10..100** | measured | **135** | **12,285** | 0 | **71** | **19** | **0** |
| **10** | **91** | **10..100** | measured | **108** | **9,828** | 0 | **67** | **15** | **0** |
| **10** | **291** | **10..300** | labels | **135** | **39,285** | **152** | **124** | **66** | **0** |
| **10** | **291** | **10..300** | labels | **108** | **31,428** | **152** | **109** | **53** | **0** |
| **10** | **291** | **10..300** | measured | **135** | **39,285** | **152** | **124** | **66** | **0** |
| **10** | **291** | **10..300** | measured | **108** | **31,428** | **152** | **109** | **53** | **0** |

**The finding that decides §2.** Positions whose **cycle label differs** between
the two conventions:

| window | all 135 | non-test 108 |
|---|---|---|
| start=1, n=25 | 1,150 | 925 |
| start=1, n=100 | 4,600 | 3,700 |
| **start=10, n=91 (10..100)** | **0** | **0** |
| start=10, n=291 (10..300) | 152 | 152 |

At `start=10` the two conventions return the **same cycle labels, the same mask
and the same cell set** — 0 differing positions. They can only differ where a
placeholder or an absent label falls inside the window, the placeholder is only
ever label 1, and there are no interior gaps (§1.1). The 152 at n=291 are not a
convention difference at all: they are the single cell with 148 requestable
cycles running out, and the only thing that differs is the *label reported* at an
absent position (see §2.2, rule 6).

The 152 absent positions at `start=10, n=291` are one cell (`short_cells = 1`);
no cell is short of 100 cycles, and none of 25 or 50.

### 1.3 What the masked positions in the team's window actually are

Inside labels 1..25, the 93 series-invalid positions (all 135 cells) decompose as:
**46** placeholders (label 1, 2017-05-12); **25 of 25** for `EL150800453240`
(inside its cycles 1–53 splice run); a **labels 12–13 cluster** of 17 rows across
16 cells of 2017-05-12, plus 1 more row at label 13 in 2018-04-12 (18 rows / 17
cells in total — `USAGE.md`:655 scopes its "17 across 16" to that batch, which is
correct as written); and **6** positions failing `series_grid_in_range`.

Dropping label 1 is therefore worth **46 of the 93** masked positions and **29 of
the 48** droppable cells; it is the whole of the NaN. Everything after label 10 is
unaffected by the convention.

### 1.4 Payload cost of the team's windows (3 grid fields, float32)

| window | 135 cells | 108 cells |
|---|---|---|
| n=25 | 0.041 GB | 0.032 GB |
| n=91 (10..100) | 0.147 GB | 0.118 GB |
| n=291 (10..300) | 0.471 GB | 0.377 GB |

All well under `DEFAULT_MAX_BYTES` (2 GiB). The 10..300 window over all 135 cells
with all three grid fields is the largest call this workflow makes, at 0.47 GB.

---

## 2. `window=` — the exact signature change

### 2.1 Signature

```python
def load_series(
    cell=None,
    cycles=None,
    fields=C.V11_GRID_FIELDS,
    clean=False,
    require_series_valid=True,
    beyond_crossing=False,
    include_test=False,
    drop_invalid_cells=False,
    max_bytes=DEFAULT_MAX_BYTES,
    data_dir=None,
    v11_dir=None,
    window="labels",   # NEW  "labels" | "measured"
    start=None,        # NEW  first cycle *label* of the window
    n=None,            # NEW  window length, in positions
):
```

Three parameters **appended at the end**, nothing reordered, nothing removed, no
`*` marker introduced. A `*` before `clean` would be cleaner to read but would
break any existing positional call, and a patch release must not do that. The
docstring documents them immediately after `cycles=`, where they belong
logically.

No other public signature changes. `load_vdlin`, `open_batch` and every v0.2.x
entry point are untouched.

### 2.2 Semantics, as rules

1. **`window="labels"` (default) is bit-for-bit the current behaviour.** `cycles=`
   means cycle labels as stored; the returned positions are the requested labels
   in the requested order; a label with no row comes back `present=False` keeping
   its label.
2. **`start=` is always a cycle label**, never an ordinal, under both conventions.
   `n=` is always a count of returned positions.
3. `start`/`n` must be given **together**; either alone raises `ValueError`.
   `cycles=` and `start`/`n` are **mutually exclusive**; passing both raises.
4. `window="labels"` + `start=a, n=k` is exact sugar for
   `cycles=range(a, a + k)`.
5. `window="measured"` + `start=a, n=k` returns, **per cell**, the first `k` rows
   with `is_placeholder == False` and `cycle >= a`, in ascending label order.
   With `a = 1` that is literally "the first N non-placeholder cycles per cell".
6. `window="measured"` where a cell has fewer than `k` such rows: the trailing
   positions are **padded with label `0` and `present=False`** — the same padding
   the existing `cycles=None` path already uses. (Under `labels` those same
   positions carry the requested label with `present=False`. This is the only
   difference the two conventions show at `start=10`, and it is a difference in
   the *reported label of an absent position*, not in any measurement.)
7. `window="measured"` + `cycles=` given explicitly → `ValueError` naming
   `start=`/`n=`. An arbitrary label set has no meaning under a convention that
   re-indexes; refusing it beats guessing.
8. `window="measured"` + `cycles=None` → every non-placeholder row of each cell,
   i.e. the current `cycles=None` result minus the 46 placeholder positions.
9. Anything other than `"labels"` or `"measured"` → `ValueError` listing both.
10. **Unchanged by this release:** gaps are never closed; `len(result) == n`
    always; labels are always returned; nothing is interpolated, zero-filled,
    clipped or renumbered; every file opens `mode="r"`. `window="measured"` does
    not *fill* anything — it **selects** different rows, and says so in
    `filters`.

### 2.3 Return-value changes

Shapes and keys are unchanged. `filters` gains three entries and sharpens one:

```python
"window": "labels" | "measured",
"start":  None | int,
"n":      None | int,
"cycles": "all" | [int, ...] | "measured:start=10,n=91",
```

`cycle`, `valid`, `present`, `is_placeholder`, `is_series_valid`,
`beyond_crossing`, `is_clean_cycle`, `n_samples`, `segment`,
`source_batch_date` keep their shapes and meanings. Under `measured` the `cycle`
matrix is already per-cell — the existing `cycles=None` branch builds exactly
such a per-cell label grid — so **no return-shape change is needed at all**.

### 2.4 Implementation shape (≈30 lines, one branch)

`load_series` already has two label-grid branches: `cycles=None` (per-cell) and
explicit `cycles=` (tiled). `measured` is a third branch in the same place,
building `grid_labels` per cell from the already-filtered `sub` index. Everything
downstream — the `req` merge, `present`, the flag joins, the mask,
`drop_invalid_cells`, `_estimate_bytes`, the per-file read loop — is reached
unchanged, because all of it consumes `grid_labels`. Validation of the new
arguments goes next to `_normalise_cycles`. No new module, no new dependency, no
change to `_h5.py`.

### 2.5 Default, version number, deprecation — the recommendation

**Keep `window="labels"` as the default. Release it as 0.3.1. No deprecation
path, because nothing is deprecated.**

1. It is the current behaviour, so the release is purely additive and **no caller
   changes meaning**.
2. The team's own regime makes the default moot: at `start=10` the two
   conventions are identical in every returned value (§1.2, 0 differing
   positions). The historical case for a `measured` default — "zero NaN in the
   array" — only ever applied to windows that contain label 1, and the team has
   decided cycle 1 is not an input.
3. `measured` as the default would weaken the module's loudest promise. Promise 1
   is "invalid and placeholder cycles are returned, masked — never silently
   dropped". A default that *selects past* 46 placeholder rows is a default that
   drops them. It should be opt-in and named at the call site.
4. The labels convention is the one in which **label 10 is the same physical
   cycle in every batch** — the team's stated convention — and the one the paper's
   ΔQ(100−10) feature is defined in. Under `measured` with `start=1`, 46 cells
   are label-shifted by one and 1,150 of 3,375 positions carry a different label.
5. 0.3.1 is the honest number: three appended keyword arguments, a behaviour-
   preserving default, no removals, no positional renumbering. **0.4.0 would be
   the right number only if the default flipped** — and the way to find out
   whether it should is a release where `measured` exists, is documented as the
   recommended setting for label-1-inclusive windows, and is tried. If it is ever
   flipped, that is a minor bump with a one-release `window=None` sentinel warning
   first; this plan explicitly does **not** schedule that.

**Documented recommendation for the team**, in `USAGE.md` and the docstring:
`window="labels"` with `start=10` — which is what they already decided, and which
(§1.2) costs nothing relative to `measured`. `window="measured"` is for the one
question it answers better: "give me N real measurements per cell from the very
beginning of life", where `start=1`.

### 2.6 The docstring bug this fixes

`matr_clean/series.py`:362–364 currently reads:

> `drop_invalid_cells`: `True` removes a whole cell when **any** row in the
> requested range is series-invalid. Off by default: at a 25-cycle window it
> costs **18 of 135 cells** to recover **48 of 3,375** positions […]

Two errors in one sentence. 18 / 48 is the **measured**-convention pair, quoted on
a function that implements the **labels** convention (`cycles=` takes labels —
there was no `window=` to choose in 0.3.0). And "135 cells" is the
`include_test=True` population, while the function defaults to
`include_test=False`, i.e. 108. Re-derived by calling the shipped loader:

| call | cells returned | masked positions | cells droppable |
|---|---|---|---|
| `load_series(cycles=range(1,26), include_test=True)` | 135 | **93** | **48** |
| `load_series(cycles=range(1,26))` (default, non-test) | 108 | **80** | **39** |

Both agree exactly with §1.2's independently computed rows, which is the check
that the figures in this plan describe the shipped code and not a model of it.
The replacement sentence quotes the default population first (39 of 108 cells for
80 of 2,700 positions, labels), then the `measured` pair (14 of 108 for 44), then
points at the §1.2 table.

---

## 3. `load_early_window` — recommendation: **do not build it**

`SPEC_v0.2.md` §3/§6 specified it, `SPEC_v0.3.md` §8.2 step 4 deferred it to
0.3.1 with "built here if it stays thin". It should now be **closed as won't-do**,
and the specs amended to say so.

* Once `window=` and `start`/`n` exist, the wrapper is
  `load_series(start=1, n=25, fields=GRID)` with the arguments spelled out — it
  saves nothing but hides which convention is in force, which is the one thing a
  caller of an early window must know.
* Its specified defaults are now **wrong for this project**: `n_cycles=25`,
  `window="measured"`, start at cycle 1. The team trains from **label 10** with
  k from 100 under the labels convention. A helper whose defaults contradict the
  documented workflow is worse than no helper.
* It is a **prefix helper**, and the team decided there is no prefix helper. §4's
  "load once, slice prefixes" is the replacement, and it is strictly more capable:
  one 10..300 call feeds every k from 100 to 300 with no re-read.
* It would have returned a stacked `X (n, 25, 3, 1000)`, a **second array layout**
  for the same data, and a second place for the mask contract to drift out of
  step.
* Nothing in the repo depends on it. `features.py`:535 and
  `SPEC_v0.3.md`:308/842's alignment contract are already expressed against
  `load_series` / `load_conditioning` and are already tested (test **i**).

**Cost of saying no:** `SPEC_v0.2.md` §6's "recommended default
`window="measured"`" and `SPEC_v0.3.md` §2.2's signature become historical, and
`tests/test_v11_integration.py`:277's "`window="measured"` (the chosen default)"
becomes wrong. All three are in §5's fix list.

---

## 4. `USAGE.md` — the new section "Load once, slice prefixes"

Placed immediately after "The early-cycle window", which it supersedes. Content,
in order:

1. **One call, then slicing.** `data = mc.load_series(cycles=range(10, 301),
   fields=("Qdlin",))` once; then `data["Qdlin"][:, :k - 9]` and
   `data["valid"][:, :k - 9]` for each k. The mask is sliced **with** the array,
   every time, as one object — never re-derived, never dropped. Labels come from
   `data["cycle"][:, :k - 9]`, so the prefix's identity is never inferred from a
   position.
2. **Expanding windows**: k from 100 to 300, prefix `[:, :k - start + 1]`.
   **Rolling windows**: `[:, j:j + L]`. Both are slices of the one array; neither
   needs a second read. The 0.47 GB figure from §1.4 is the whole cost.
3. **Why label 10.** Label 1 of the 46 cells of 2017-05-12 is the zero-filled
   placeholder (§1.1): an all-NaN grid row in the array, a literal `0.0` in the
   native fields where NaN-checking cannot see it. Starting at label 10 excludes
   it outright, which is why `window="labels"` and `window="measured"` return
   identical results there (§1.2) and why `window=` can be left alone.
4. **Split by cell, never by window.** Prefixes of one cell share its degradation
   trajectory and its cell-level artifacts; a window-level split leaks a cell's
   future into training. Split `cell_uid` (`mc.load_splits()` / `fold`), then take
   every window of a training cell. The 27 `fold == -1` cells stay out until the
   end.
5. **Fit normalization on valid positions of training cells only.** Statistics
   from `X[train][valid[train]]`, nothing else: not on test cells, not on masked
   positions. One out-of-band `Qdlin` position is ~45 Ah against a 1.1 Ah nominal
   and will ruin a scaler on its own (§1.3), and 6 such positions sit inside
   labels 1..25.
6. **Masked-mean loss.** `(err * m).sum() / m.sum()` with
   `m = valid[:, :k].astype(float)`, not `err.mean()`, and guard `m.sum() == 0`.
   A plain mean over a padded prefix trains the model on fabricated zeros.
7. **Fill only after normalization, and always pass the mask onward.** If a
   framework needs a dense tensor, fill **after** the statistics are fitted and
   with the mask travelling alongside into the loss. Filling before
   normalization puts the fill value into the statistics; filling without
   carrying the mask makes the fill indistinguishable from a measurement. The
   loader itself fills nothing — that is promise 1, and it is AST-tested (§6).
8. **`is_clean_cycle == -1`** — cross-reference to §5's new paragraph.

No code is added to `matr_clean/` for this section. It is documentation of
slicing the user already can do.

---

## 5. Documents and docstrings to fix

### 5.1 The stale v0.3.0 promise, and the `window=`/`load_early_window` promise

| file | line(s) | what it says now | fix |
|---|---|---|---|
| `matr_clean/series.py` | 362–364 | `drop_invalid_cells` "18 of 135 cells … 48 of 3,375" | §2.6: labels pair for the default 108-cell population, then the measured pair, then point at the table |
| `matr_clean/series.py` | 336–340 | `cycles=`'s parameter doc says "cycle labels" but never names the convention or its cost | state that `cycles=`/`start=` are the **labels** convention, name `window=`, cross-reference |
| `matr_clean/series.py` | 1–45 (module) | "Rolling windows need no other function" loop starts at label 1, step 25 | restate with `start=10`; add the `window=` rule and the §1.2 identity-at-10 finding |
| `matr_clean/series.py` | 69–76 (`CLEAN_NOT_JUDGED`) | explains `-1` but only in a comment | keep, and make the public docstring say it (§5.2) |
| `matr_clean/__init__.py` | 30, 112 | "As of v0.3.0 …" / "# v0.3.0 — the within-cycle series" | retag as shipped; bump `__version__` to `0.3.1` (line 98) |
| `matr_clean/constants.py` | 118, 180 | "The HDF5 files arrive with v0.3.0" / "Read by v0.3.0" | present tense |
| `matr_clean/features.py` | 18, 330 | "those arrive with v0.3.0" | point at `load_series` |
| `matr_clean/features.py` | 535 | **already fixed upstream** — reads "a row order `load_series` reproduces exactly". `SPEC_v0.3.md`:905 still lists it as outstanding | no code change; strike the row from §8.3 of the spec |
| `matr_clean/loaders.py` | 718–727 | field table tags nine series + `Vdlin` "v0.3.0" | retag as shipped |
| `pyproject.toml` | 7 | `version = "0.3.0"` | `0.3.1` |
| `pyproject.toml` | `series` comment | "v0.3.0 reads the three HDF5 files" | present tense; keep the measured h5py 3.12.1 floor note |
| `README.md` | 285 | "reads these files as of **v0.3.0**" | `v0.3.1`, and mention `window=` in one clause |
| `USAGE.md` | 583–587 | "Inside the first 25 cycles … 93 invalid positions across 48 of the 135 cells" | correct as measured (§1.2); add the non-test pair (80 / 39 of 108), which is what the default call returns |
| `USAGE.md` | 598–603 | "### The early-cycle window" / "v0.3.0 ships no dedicated early-window function" | rewrite: `window=` ships; `load_early_window` is won't-do; link §4 |
| `USAGE.md` | 605–620 | the hand-rolled `groupby(...).head(25)` recipe for the measured convention | replace with `window="measured", start=1, n=25` |
| `USAGE.md` | 622–637 | the 10/25/50 cost table, all-135 only | keep (all nine values verify), add the 108 rows, add `start=10` rows, add the "0 differing positions at start=10" line |
| `USAGE.md` | 650–672 | "What the first 25 cycles actually contain" + `drop_invalid_cells` 18/48 | keep the forensics (they verify); state which population each number is |
| `USAGE.md` | 784, 813–831 | field table / "**v0.3.0** reads the rest" | retag as shipped |
| `USAGE.md` | 325, 542 | "in v0.3.0" | present tense |
| `SPEC_v0.3.md` | 3–6 | "approved and built, except `load_early_window` … awaits review" | amend: closed won't-do in 0.3.1 (§3) |
| `SPEC_v0.3.md` | 33, 378, 381–428, 689, 884, 888, 1030 | `load_early_window` as a planned wrapper, with signature and defaults | mark superseded by `window=`/`start`/`n`; keep as a record of the decision |
| `SPEC_v0.3.md` | 407–408 | "`window="measured"` (the default)" | the default is `"labels"` (§2.5) |
| `SPEC_v0.3.md` | 522, 534–535 | the §2.7 cost tables | values verify; add the 108-cell and `start=10` rows |
| `SPEC_v0.3.md` | 891–909 | §8.3's own "docs that promise v0.3.0 behaviour" list | mark each row done or superseded; this table replaces it |
| `SPEC_v0.3.md` | 960, 965–971 | "does cycle 1 matter?" left open | answered by the team: no (§0); record the decision and the start=10 identity |
| `SPEC_v0.2.md` | 3, 28–38, 262, 301–349, 458, 483–505, 548 | `load_early_window`, and "recommended default `window="measured"`" | one superseded-by note at §3/§6; do not rewrite history |
| `tests/test_v11_integration.py` | 277 | docstring: "`window="measured"` (the chosen default)" | "the opt-in convention"; assert against `window=` directly |
| `tests/test_v11_series_integration.py` | 342 | "no thermal extreme inside 25 cycles" | keep; add the start=10 analogue |

A new **`SPEC_v0.3.1.md`** is *not* proposed: the delta is three keyword
arguments. This plan file plus the amendments above are the record.

### 5.2 `is_clean_cycle == -1` — to be documented explicitly

New short paragraph in `USAGE.md` (field table + the prefix section) and in
`load_series`'s own `Returns` block:

> `is_clean_cycle` is `int8` with **three** states: `1` clean, `0` dirty, and
> **`-1` = v1.0 never judged this row**. `-1` is not "dirty". It appears for the
> **1,179 `beyond_crossing` cycles** (of 114,738), which have no row in
> `analysis_set_cycles.csv` because that file is truncated at each cell's 80% SOH
> crossing, and for any requested label with no row at all. With the default
> `beyond_crossing=False` those cycles are excluded from the request entirely, so
> `-1` then only marks absent labels — a labels-convention window over 10..100
> returns **zero** `-1` positions. Filter with `is_clean_cycle == 1`, never with
> `is_clean_cycle != 0` and never by truthiness: `-1` is truthy and `bool(-1)` is
> `True`.

`CLEAN_NOT_JUDGED = -1` is already the module constant and stays public.

---

## 6. Tests

Added to `tests/test_v11_series.py` (fixture-level, offline) and
`tests/test_v11_series_integration.py` (real data, gated on
`MATR_CLEAN_TEST_DATA`). The series fixture holds 3 cells / 12 rows / **1
placeholder** (`EL150800460514`, label 1), which is enough for every unit-level
assertion.

| # | test | level | asserts |
|---|---|---|---|
| 1 | `measured` vs `labels` on the placeholder cell | fixture | for `EL150800460514`, `labels start=1,n=3` → labels 1,2,3 with position 0 masked and all-NaN grid; `measured start=1,n=3` → labels 2,3,4, nothing masked, no NaN |
| 2 | the placeholder population | real | 46 of 135 cells and 37 of 108 non-test carry a placeholder; every one is at label 1 and in 2017-05-12 |
| 3 | `start=1, n=25` cost, both conventions | real | masked/cells = 93/48 and 48/18 (135 cells); 80/39 and 44/14 (108). The numbers §2.6 replaces |
| 4 | **`start=10` identity** | real | `labels` and `measured` at `start=10, n=91` return **identical** `cycle`, `valid`, `present` and cell sets; masked/cells = 71/19 (135), 67/15 (108) |
| 5 | `start=10, n=291` | real | 152 absent positions in one cell; under `measured` those carry label `0`, under `labels` they carry 149..300; both `present=False`; masked/cells = 124/66 (135), 109/53 (108) |
| 6 | `start`/`n` sugar | fixture | `window="labels", start=a, n=k` is element-wise identical to `cycles=range(a, a+k)` for every returned key |
| 7 | argument errors | fixture | `start` without `n`; `n` without `start`; `cycles=` with `start`/`n`; `window="measured"` with `cycles=`; `window="nonsense"` — each a `ValueError` naming the alternative |
| 8 | `window="measured", cycles=None` | fixture | returns each cell's rows minus its placeholder; `len` drops by exactly the placeholder count; no NaN row |
| 9 | **AST repair-call test still absolute** | fixture | the existing `test_e_source_contains_no_repair_call` over `series` and `_h5` still finds **zero** of `nan_to_num, fillna, clip, interp, ffill, bfill, dropna, interpolate, nan_to_zero` — the new branch adds none |
| 10 | `is_clean_cycle` tri-state | real | `-1` count is 0 for a 10..100 labels window; `beyond_crossing=True` over a full cell yields `-1` exactly on rows absent from `analysis_set_cycles.csv`; `(x == 1)` and `(x != 0)` differ |
| 11 | `filters` records the request | fixture | `window`, `start`, `n` present and correct; `cycles` reads `"measured:start=10,n=91"`; `repaired` unchanged |
| 12 | promises 1–4 under `measured` | fixture | `len(result) == n`; labels always returned; nothing interpolated; files opened `mode="r"` |

**Matrix** — 6 environments, pandas × h5py, Python 3.13.5:

| | h5py 3.12.1 | h5py 3.16.0 |
|---|---|---|
| pandas 2.2.3 | ✓ | ✓ |
| pandas 3.0.6 | ✓ | ✓ |
| pandas 3.1.1 | ✓ | ✓ |

Throwaway venvs under `$CLAUDE_JOB_DIR/tmp`, never in the repo. `pandas==2.2.3`
has a `cp313` wheel (verified by download). **Offline**: `tests/conftest.py`
replaces `urlopen` with one that raises and points the cache at `tmp_path`, so
the suite cannot reach the network; the `network` marker stays opt-in via
`MATR_CLEAN_TEST_NETWORK=1` and is not set. Each env runs twice — fixture-only,
then with `MATR_CLEAN_TEST_DATA` — giving 12 runs reported as two counts per env.

**Baseline on `1dbe475`, measured today:** `280 passed, 66 skipped` offline and
`344 passed, 2 skipped` with real data. One caveat worth recording: a *fresh*
worktree has no `exploration/extract_out/` (it is self-ignoring and never
committed), and `tests/test_v11_series.py::test_n_v02_functions_do_not_need_h5py`
then **fails** with `DownloadError`, because it calls
`load_cycle_features(data_dir=exploration_dir)` and the v1.1 index is not there.
It passes in the main checkout. Not a code defect and not in scope; Stage B runs
with the three published files symlinked (read-only) into the worktree's
`exploration/extract_out/`, which git ignores. If it should instead skip when the
v1.1 files are absent, say so and it becomes a one-line `pytest.skip` in 0.3.1.

---

## 7. Risks

| risk | size | handling |
|---|---|---|
| Appending `window`/`start`/`n` after `data_dir`/`v11_dir` reads oddly | cosmetic | deliberate: no positional breakage in a patch release. Docstring orders them logically; a future minor release may add `*` |
| Someone reads `window="measured"` as "repair the placeholders" | real | it **selects** rows and never fills; `filters["repaired"]` still says "nothing"; the AST test (6.9) keeps it true; the docstring says "selects, does not fill" |
| `measured` padding with label `0` could be mistaken for a cycle | low | label 0 does not exist (labels start at 1) and `present=False` marks it; test 5 pins both |
| The `-1` tri-state is filtered with `!= 0` | real, pre-existing | §5.2 documents it and test 10 pins that `== 1` and `!= 0` differ |
| 0.3.1 vs 0.4.0 judged wrong later | low | nothing is deprecated and no default moves, so a later flip is still a clean minor bump with a sentinel warning |
| Matrix needs PyPI for 6 venvs | medium | network already verified reachable; wheels cached in `$CLAUDE_JOB_DIR/tmp/wheels`. If it drops, Stage B reports which cells ran and which did not, rather than claiming six |
| Figures drift from the files | handled | every number here is computed, and §2.6's pair was re-derived through the shipped `load_series`; the tests in §6 re-assert the ones that appear in prose |

---

## 8. What Stage B does, in order

1. `window`/`start`/`n` in `series.py` (§2.1–2.4) + validation.
2. Docstrings in `series.py`, including the §2.6 fix and the §5.2 `-1` paragraph.
3. Version bump to `0.3.1` (`__init__.py`, `pyproject.toml`).
4. `USAGE.md` §4's new section, plus its rows in §5.1.
5. The remaining §5.1 doc fixes, `SPEC_v0.3.md`/`SPEC_v0.2.md` amendments last.
6. The twelve tests of §6.
7. The 6-env matrix, twice each; report diff stat and both counts per env.
8. Propose the tag `loader-v0.3.1` (annotated, on the 0.3.1 commit) and **stop**.
   No tag is created and nothing is pushed without an explicit "push".
