"""Build the analysis-ready view of the dataset, for predicting WHEN 80% SOH is crossed.

This is a DERIVED VIEW, not a cleaned dataset. The raw .mat files are untouched and
re-reading them reproduces everything here. Two outputs:

  analysis_set_cells.csv   one row per physical cell  (the modelling unit)
  analysis_set_cycles.csv  one row per cycle, truncated at the crossing

Decisions baked in, per the agreed scope:

D0  SOH is measured against the 1.1 Ah NOMINAL capacity, so 80% SOH = 0.88 Ah.
    Not against each cell's own initial capacity: cells start at ~1.07 Ah, which puts
    0.88 Ah at 81.5-82.6% of initial, and under an 80%-of-initial rule only the 43
    cells of 2017-06-30 would ever cross -- the other 92 stop above it. Nominal is also
    a single global constant rather than a per-cell one.

D1  Cycle life is `cycle_life_cycles` from the inventory: the measured 0.88 Ah crossing
    where the cell was cycled past it (2017-06-30), the test-termination cycle where the
    test stopped at the criterion (the other two batches, within <=1 cycle of it).

D2  2017-06-30 is kept and TRUNCATED at its crossing, since cycles below 0.88 Ah are out
    of scope. This costs 1179 of 21527 cycles in that batch and puts all three batches on
    one basis. `batch_date` is retained as a factor: the batches differ in CV cutoff
    (C/50 vs C/20), rest scheme and baseline temperature, which shape the capacity
    trajectory itself.

D3  The 5 paused-and-resumed cells are JOINED but marked. Their junction injects a step
    of 1.4-5.0% of the cell's whole degradation range in a single cycle (up to 183 cycles
    of equivalent ageing, in the wrong direction), so they are excluded from trajectory
    training by default via `use_for_trajectory`. Flip that column to include them. They
    are kept for crossing-time work, where the junction does not affect the label.

D4  Censored cells are KEPT with `has_eol_label = False`. Their trajectory is valid up to
    where they stop; only the crossing-time label is missing.

D5  Our own selection. `in_paper_124` marks Severson et al.'s subset for optional
    comparison. No cell is dropped on that basis.

Nothing is masked or interpolated. Known-bad cycles are flagged per cycle and left
in place for the modelling step to filter:

* `is_measured_cycle` -- the row is a measurement at all. False only for
  2017-05-12's zero-filled cycle 1, which the struct retains as a placeholder.
  (Named `cycle_valid` before 2026-10-27; that name read like a general
  usability flag, which it never was.)
* `is_artifact_cycle` -- QDischarge departs from a centred 11-cycle rolling
  median by more than 0.01 Ah.
* `is_restart_cycle` -- chargetime indicates the cycle spans a test interruption.
* `is_junction_cycle` -- within 2 cycles of a continuation seam.
* `is_clean_cycle` -- the conjunction: measured and none of the three above. This
  is the convenience column for modelling; the four it derives from stay so that
  any individual reason remains visible.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matr
from checks import _meta, _valid_summary
from inventory import first_valid_index

TABLES = HERE / "tables"
NOMINAL = matr.NOMINAL_CAPACITY_AH      # 1.1 Ah
EOL = matr.EOL_THRESHOLD_AH             # 0.88 Ah = 80% of nominal
JUNCTION_HALF_WIDTH = 2                 # cycles each side of a continuation junction

# --- cross-validation split (B1) -----------------------------------------
# Fixed on 2026-10-27 and not to be changed; the whole point of a stored fold
# column is that every run and every model sees the same partition.
SPLIT_SEED = 20261027
N_FOLDS = 5
TEST_FRACTION = 0.20
TEST_FOLD = -1          # sentinel for the held-out cells

# --- thermocouple fault (B2) ---------------------------------------------
# Two independent signatures, each with its own cutoff (REPORT.md 4.3.1):
#   poor contact throughout -> charge-heat residual well below the batch fit
#   contact lost mid-test    -> T_rise steps down from early to late life
# Cutoffs sit in the gap between ranks 6 and 7 (-3.39 / -2.76 C) and ranks 4
# and 5 (-2.07 / -1.13 C) of 140 respectively.
TC_RESID_MAX_C = -3.0
TC_LATE_STEP_MAX_C = -2.0

# Severson et al.'s published subset, by channel (see cleaning_plan.md issue 14)
PAPER_EXCLUDED = {
    "2017-05-12": {13, 19, 21, 22, 31},          # censored, "do not reach 80%"
    "2018-04-12": {6, 7, 12, 33, 41, 46},        # "noisy", incl. the 2 censored
}


def thermocouple_evidence() -> dict[tuple[str, int], tuple[bool, str]]:
    """Per (batch_date, channel): does this cell show a thermocouple fault, and why.

    Returns the verdict and a human-readable evidence string, kept in a separate
    column so the boolean never has to be taken on trust. Ranks are over all 140
    struct rows, so they are comparable across batches.
    """
    t = pd.read_csv(TABLES / "thermocouple_outliers.csv")
    t["resid_rank"] = t["T_rise_resid_C"].rank(method="min").astype("Int64")
    t["late_rank"] = t["T_rise_late_minus_early_C"].rank(method="min").astype("Int64")
    n = len(t)
    out = {}
    for r in t.itertuples():
        measured = []
        if pd.notna(r.T_rise_resid_C) and r.T_rise_resid_C <= TC_RESID_MAX_C:
            measured.append(f"charge-heat residual {r.T_rise_resid_C:+.2f} C "
                            f"(rank {int(r.resid_rank)}/{n}, cutoff "
                            f"{TC_RESID_MAX_C:+.1f})")
        if (pd.notna(r.T_rise_late_minus_early_C)
                and r.T_rise_late_minus_early_C <= TC_LATE_STEP_MAX_C):
            measured.append(f"late-life T_rise step "
                            f"{r.T_rise_late_minus_early_C:+.2f} C "
                            f"(rank {int(r.late_rank)}/{n}, cutoff "
                            f"{TC_LATE_STEP_MAX_C:+.1f})")
        # The page note is recorded as corroboration but never decides the flag:
        # the verdict stays a measurement, so a cell the pages miss is still caught
        # and a cell the pages name is still checked.
        evidence = list(measured)
        # Only the thermal half of page_note is corroboration here; that column
        # carries every note for the cell, including continuation and censoring.
        note = "" if pd.isna(r.page_note) else str(r.page_note)
        thermal = [x.strip() for x in note.split(";")
                   if "thermocouple" in x.lower() or "temperature" in x.lower()]
        if thermal:
            evidence.append("page: " + "; ".join(
                x.removeprefix("page:").strip() for x in thermal))
        out[(r.batch_date, int(r.channel))] = (bool(measured), "; ".join(evidence))
    return out


def assign_folds(cells: pd.DataFrame) -> pd.Series:
    """Seeded, grouped, stratified fold assignment -- see MANIFEST.md.

    * **Grouped by barcode.** One row per physical cell and `cell_uid == barcode`,
      so every cycle of a cell -- including both segments of a cell that was
      continued into a later batch -- lands in exactly one fold. No cell is ever
      split across folds, which is the only grouping that matters here: cycles
      within a cell are strongly correlated and would leak otherwise.
    * **Stratified on (batch_date, has_eol_label).** Batch because the three
      batches differ in cycling protocol and chamber behaviour; label presence
      because the 7 censored cells cannot contribute to a target-based metric and
      must not pile up in one fold.
    * **Fixed held-out test cells** carry fold == -1 and are never used for
      training or model selection. They are drawn first, before the CV folds, so
      adding or removing folds later cannot disturb them.
    """
    rng = np.random.default_rng(SPLIT_SEED)
    fold = pd.Series(np.full(len(cells), np.nan), index=cells.index, dtype=float)
    deal = 0   # runs across strata, so fold sizes stay even overall
    for _, g in cells.groupby(["batch_date", "has_eol_label"], sort=True):
        # deterministic pre-shuffle order, so the seed alone fixes the result
        idx = np.array(g.sort_values("barcode").index.to_numpy(), copy=True)
        rng.shuffle(idx)
        n_test = int(round(TEST_FRACTION * len(idx)))
        fold.loc[idx[:n_test]] = TEST_FOLD
        for i in idx[n_test:]:
            fold.loc[i] = deal % N_FOLDS
            deal += 1
    assert fold.notna().all()
    return fold.astype(int)


def build():
    inv = pd.read_csv(HERE / "cell_inventory.csv")
    inv = inv[inv.in_struct].copy()
    flags = pd.read_csv(TABLES / "cell_flags.csv")
    spikes = pd.read_csv(TABLES / "capacity_spikes.csv")
    gaps = pd.read_csv(TABLES / "time_gaps.csv")

    spike_set = set(zip(spikes.batch_date, spikes.channel, spikes.cycle))
    gap_set = set(zip(gaps.batch_date, gaps.channel, gaps.cycle))
    cls = {(r.batch_date, r.channel): r.cell_class for r in flags.itertuples()}
    tc = thermocouple_evidence()
    # B3: the policy string exactly as the struct stores it, per segment
    stored_policy = {r.cell_uid: r.policy_as_stored_all_segments
                     for r in inv.itertuples()}
    def _txt(v):
        return v if isinstance(v, str) and v.strip() else ""

    reasons = {(r.batch_date, r.channel):
               " | ".join(x for x in (_txt(r.page_notes), _txt(r.data_reasons)) if x)
               for r in flags.itertuples()}

    meta = {d: {r.channel: r for r in _meta()[d]} for d in matr.BATCH_DATES}

    cell_rows, cyc_rows = [], []
    for _, r in inv.iterrows():
        segs = [s.split(":ch") for s in r.all_segments.split(" | ")]
        eol_cycle = r.cycle_life_cycles              # NaN for censored
        has_label = bool(np.isfinite(eol_cycle))

        # --- assemble the (possibly joined) series
        cyc, qd, seg_id, src = [], [], [], []
        offset = 0.0
        junctions = []
        for k, (d, ch) in enumerate(segs):
            ch = int(ch)
            s, _ = _valid_summary(meta[d][ch]) if False else (meta[d][ch].summary, None)
            n = len(s["cycle"])
            cyc.append(s["cycle"] + offset)
            qd.append(s["QDischarge"])
            seg_id.append(np.full(n, k + 1))
            src.append(np.array([(d, ch)] * n, dtype=object))
            offset += n
            if k < len(segs) - 1:
                junctions.append(offset)
        cyc = np.concatenate(cyc); qd = np.concatenate(qd)
        seg_id = np.concatenate(seg_id); src = np.concatenate(src, axis=0)

        # --- 2017-05-12's zero-filled cycle 1 is not a measurement
        k0 = first_valid_index(qd)
        valid = np.ones(len(qd), bool)
        valid[:k0] = False

        # --- truncate at the crossing: cycles beyond 80% SOH are out of scope
        keep = np.ones(len(cyc), bool) if not has_label else (cyc <= eol_cycle)
        n_truncated = int((~keep).sum())

        # --- per-cycle flags
        is_art = np.array([(d, int(c), float(cc)) in spike_set
                           for (d, c), cc in zip(src, cyc)])
        is_rst = np.array([(d, int(c), float(cc)) in gap_set
                           for (d, c), cc in zip(src, cyc)])
        is_jun = np.zeros(len(cyc), bool)
        for j in junctions:
            is_jun |= np.abs(cyc - j) <= JUNCTION_HALF_WIDTH

        first_seg_d, first_seg_ch = segs[0][0], int(segs[0][1])
        key = (first_seg_d, first_seg_ch)
        in_paper = not any(int(ch) in PAPER_EXCLUDED.get(d, set()) for d, ch in segs)

        for i in np.flatnonzero(keep):
            cyc_rows.append({
                "cell_uid": r.cell_uid,
                "batch_date": first_seg_d,
                "channel": first_seg_ch,
                "cycle": float(cyc[i]),
                "segment": int(seg_id[i]),
                "QD_Ah": float(qd[i]),
                "soh": float(qd[i]) / NOMINAL,
                "cycles_to_eol": float(eol_cycle - cyc[i]) if has_label else np.nan,
                "is_measured_cycle": bool(valid[i]),
                "is_artifact_cycle": bool(is_art[i]),
                "is_restart_cycle": bool(is_rst[i]),
                "is_junction_cycle": bool(is_jun[i]),
                "is_clean_cycle": bool(valid[i] and not is_art[i]
                                       and not is_rst[i] and not is_jun[i]),
            })

        cell_rows.append({
            "cell_uid": r.cell_uid,
            "barcode": r.barcode,
            "batch_date": first_seg_d,
            "channel": first_seg_ch,
            "all_segments": r.all_segments,
            "policy_canonical": r.policy_canonical,
            # B3: kept beside the canonical form because 8 of the 139 struct rows
            # store a corrupted string (truncated head, missing trailing C,
            # -newstructure suffix) and the repair must stay auditable.
            "policy_as_stored": stored_policy.get(r.cell_uid, ""),
            "policy_C1": r.policy_C1, "policy_Q1_pct": r.policy_Q1_pct,
            "policy_C2": r.policy_C2, "policy_n_steps": r.policy_n_steps,
            # --- target
            "eol_cycle_80pct_soh": eol_cycle,
            "eol_basis": r.cycle_life_basis,
            "has_eol_label": has_label,
            "censored": bool(r.censored),
            # --- trajectory extent after truncation
            "n_cycles_kept": int(keep.sum()),
            "n_cycles_truncated": n_truncated,
            "soh_initial": float(qd[k0]) / NOMINAL,
            "soh_final_kept": float(qd[keep][-1]) / NOMINAL,
            # --- flags
            "is_continuation": bool(r.is_continuation),
            "junction_cycle": float(junctions[0]) if junctions else np.nan,
            "use_for_trajectory": bool(not r.is_continuation),
            "cell_class": cls.get(key, "ok"),
            "flag_reasons": reasons.get(key, "").strip(" |"),
            "exclude_from_deltaq_features": bool(first_seg_d == "2018-04-12"
                                                 and first_seg_ch == 46),
            "n_artifact_cycles_kept": int(is_art[keep].sum()),
            "n_restart_cycles_kept": int(is_rst[keep].sum()),
            "in_paper_124": in_paper,
            # B2: worst verdict over the cell's segments, with the evidence kept
            # in its own column so the boolean is never taken on trust.
            "thermocouple_fault": any(tc.get((d, int(ch)), (False, ""))[0]
                                      for d, ch in segs),
            "thermocouple_evidence": " || ".join(
                f"{d} ch{int(ch)}: {tc[(d, int(ch))][1]}"
                for d, ch in segs if tc.get((d, int(ch)), (False, ""))[1]),
        })

    cells = pd.DataFrame(cell_rows).sort_values(["batch_date", "channel"])
    cells["fold"] = assign_folds(cells)
    cycles = pd.DataFrame(cyc_rows)
    cells.to_csv(HERE / "analysis_set_cells.csv", index=False)
    cycles.to_csv(HERE / "analysis_set_cycles.csv", index=False)
    return cells, cycles


# --- validation -----------------------------------------------------------
# The five checks REPORT.md section 7 reports as passing, as real assertions
# rather than prose, so a regression cannot pass silently. Each raises with the
# observed value; nothing here writes or modifies anything.

def validate(cells: pd.DataFrame, cycles: pd.DataFrame) -> list[str]:
    """Assert REPORT.md section 7's five validation checks. Returns the PASS lines.

    Raises AssertionError on the first failure, naming the observed value.
    """
    lines = []

    def ck(n, msg, cond, got):
        assert cond, f"[check {n}] {msg} -- got {got}"
        lines.append(f"  PASS  [{n}] {msg}")

    label = cells.loc[cells.has_eol_label].set_index("cell_uid")["eol_cycle_80pct_soh"]

    # 1. Exactly 43 MEASURED cycles below 0.88 Ah: one per 2017-06-30 cell, each the
    #    crossing itself, none before any cell's crossing. 2017-05-12's 46 zero-filled
    #    cycle-1 placeholders also read below 0.88 Ah and are excluded by
    #    is_measured_cycle -- they are not measurements (see REPORT.md section 4.4).
    below = cycles[(cycles.QD_Ah < EOL) & cycles.is_measured_cycle]
    ck(1, f"exactly 43 measured cycles below {EOL} Ah", len(below) == 43, len(below))
    ck(1, "all of them in 2017-06-30",
       set(below.batch_date) == {"2017-06-30"}, sorted(set(below.batch_date)))
    ck(1, "one per cell", below.cell_uid.nunique() == len(below), below.cell_uid.nunique())
    ck(1, "each is that cell's own crossing cycle",
       bool((below.cell_uid.map(label) == below.cycle).all()), "a mismatch")
    early = below[below.cycle < below.cell_uid.map(label)]
    ck(1, "zero sub-threshold cycles before a crossing", len(early) == 0, len(early))

    # 2. The last kept cycle equals the label exactly, for every labelled cell.
    ck(2, "128 cells carry a label", len(label) == 128, len(label))
    last = cycles.groupby("cell_uid")["cycle"].max()
    bad = [u for u, c in label.items() if last.get(u) != c]
    ck(2, "last kept cycle == label for every labelled cell", not bad, bad[:5])

    # 3. cycles_to_eol: 0 at the crossing, never negative, NaN only for censored cells.
    at_x = cycles[cycles.cell_uid.map(label).eq(cycles.cycle)]
    ck(3, "cycles_to_eol == 0 at the crossing",
       bool((at_x.cycles_to_eol == 0).all()), "a non-zero value")
    ck(3, "cycles_to_eol never negative",
       bool((cycles.cycles_to_eol.dropna() >= 0).all()), cycles.cycles_to_eol.min())
    nan_cells = set(cycles.loc[cycles.cycles_to_eol.isna(), "cell_uid"])
    censored = set(cells.loc[cells.censored, "cell_uid"])
    ck(3, "NaN cycles_to_eol only for the 7 censored cells",
       nan_cells == censored and len(censored) == 7,
       f"{len(nan_cells)} NaN cells vs {len(censored)} censored")

    # 4. Row counts reconcile.
    ck(4, "sum(n_cycles_kept) == cycle rows",
       int(cells.n_cycles_kept.sum()) == len(cycles),
       f"{int(cells.n_cycles_kept.sum()):,} vs {len(cycles):,}")

    # 5. The paper's published selection is carried intact.
    ck(5, "135 physical cells", len(cells) == 135, len(cells))
    ck(5, "in_paper_124 sums to exactly 124",
       int(cells.in_paper_124.sum()) == 124, int(cells.in_paper_124.sum()))

    return lines


if __name__ == "__main__":
    cells, cycles = build()
    print(f"wrote analysis_set_cells.csv   {len(cells)} cells")
    print(f"wrote analysis_set_cycles.csv  {len(cycles):,} cycles")
    print()
    print("### cells by batch")
    print(cells.groupby("batch_date").agg(
        cells=("cell_uid", "size"),
        with_eol_label=("has_eol_label", "sum"),
        censored=("censored", "sum"),
        use_for_trajectory=("use_for_trajectory", "sum"),
        in_paper_124=("in_paper_124", "sum"),
        cycles_truncated=("n_cycles_truncated", "sum")).to_string())
    print()
    print("### target: cycle at which 80% SOH (0.88 Ah) is crossed")
    g = cells[cells.has_eol_label]
    print(g.groupby("batch_date")["eol_cycle_80pct_soh"].describe()
          [["count", "min", "50%", "max"]].to_string())
    print()
    print("### eol basis")
    print(cells.eol_basis.value_counts().to_string())
    print()
    print("### trajectory file")
    print(f"  rows                : {len(cycles):,}")
    print(f"  not measured (placeholder): {int((~cycles.is_measured_cycle).sum())}")
    print(f"  artifact cycles      : {int(cycles.is_artifact_cycle.sum())}")
    print(f"  restart cycles       : {int(cycles.is_restart_cycle.sum())}")
    print(f"  junction cycles      : {int(cycles.is_junction_cycle.sum())}")
    print(f"  clean cycles         : {int(cycles.is_clean_cycle.sum()):,}")
    print(f"  SOH range            : {cycles.soh.min():.4f} - {cycles.soh.max():.4f}")
    print()
    print("### folds (seed %d, %d CV folds + fixed test, grouped by barcode)"
          % (SPLIT_SEED, N_FOLDS))
    print(pd.crosstab(cells.fold, cells.batch_date, margins=True).to_string())
    print(f"  cells per fold never split: {cells.barcode.nunique()} unique barcodes "
          f"over {len(cells)} rows")
    print()
    print("### thermocouple faults")
    print(f"  flagged: {int(cells.thermocouple_fault.sum())} of {len(cells)} cells")
    tcf = cells[cells.thermocouple_fault]
    for r in tcf.itertuples():
        print(f"    {r.thermocouple_evidence}")
    print()
    print("### default training set (use_for_trajectory & has_eol_label)")
    sel = cells[cells.use_for_trajectory & cells.has_eol_label]
    print(f"  {len(sel)} cells, {int(sel.n_cycles_kept.sum()):,} cycles, "
          f"{sel.policy_canonical.nunique()} distinct policies")
    print(cells.assign(sel=cells.use_for_trajectory & cells.has_eol_label)
          .groupby("batch_date")["sel"].sum().to_string())
    print()
    print("### validation (REPORT.md section 7)")
    for line in validate(cells, cycles):
        print(line)
    print("  all five checks pass")
