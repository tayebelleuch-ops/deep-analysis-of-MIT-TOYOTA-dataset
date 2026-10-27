"""Step 1: build exploration/cell_inventory.csv -- one row per PHYSICAL cell.

Physical-cell identity is the barcode, normalised to upper case: the three
batch files are inconsistent about case (2017-05-12 writes "EL1508...", the
other two mostly "el1508..."), so a case-sensitive join would silently miss
continuations. The five cells that were paused at the end of 2017-05-12 and
resumed in 2017-06-30 therefore collapse to one row each, with both segments
listed.

Channels that have no struct row at all (2017-05-12 ch 4 and 8, and -- not
mentioned on any page -- 2018-04-12 ch 26 and 31) are emitted as rows with
in_struct=False so the channel map stays complete and the "no data" category
is countable.

Nothing is dropped, corrected or relabelled here. Columns that express a
judgement (censored, eol_*) are computed, documented, and reported alongside
the struct's own `cycle_life` field rather than replacing it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matr
import transcript_issues as ti

OUT_DIR = Path(__file__).resolve().parent
EOL = matr.EOL_THRESHOLD_AH
SUSTAIN = 5  # cycles a sub-threshold run must last to count as a real crossing

# Channels on the 48-channel Arbin that have no row in a batch's struct.
# Derived from the data (see `missing_channels`), not assumed.
ALL_CHANNELS = range(1, 49)


def first_valid_index(qd: np.ndarray) -> int:
    """Index of the first physically meaningful QDischarge entry.

    2017-05-12 keeps a placeholder row for the excluded cycle 1: all nine
    per-cycle arrays are a 2-element vector of zeros and the summary reads
    QDischarge = 0. Treating that 0 as a capacity measurement would make
    "first cycle below 0.88 Ah" return cycle 1 for all 46 cells, so the
    leading non-positive run is skipped and reported separately.
    """
    k = 0
    while k < len(qd) and (not np.isfinite(qd[k]) or qd[k] <= 0):
        k += 1
    return k


def eol_cycles(cycle: np.ndarray, qd: np.ndarray, n_recorded: int) -> dict:
    """Cycle life at the 0.88 Ah criterion -- and why it needs three columns.

    The literal definition the user asked for, "first cycle where discharge
    capacity < 0.88 Ah", is the one the paper's own LoadData.m uses
    (`find(QDischarge < 0.88, 1)`). On these files it only fires for
    2017-06-30: that batch was cycled past the threshold, ending at ~0.825 Ah,
    so the crossing is recorded. 2017-05-12 and 2018-04-12 instead STOP at the
    criterion -- their last recorded cycle sits at 0.8800-0.8834 Ah, just above
    it -- so a strict `< 0.88` test never fires and would mark both batches
    entirely censored. (This is also why the struct's own `cycle_life` field
    equals n_cycles + 1 for every cell in those two batches: it is LoadData.m's
    else-branch fallback, not a measurement.)

    So three columns are reported and none is allowed to hide the others:

    * `eol_cycle_strict_lt`  -- first cycle with QD < 0.88 Ah, or NaN.
    * `cycle_life_cycles`    -- the usable cycle life: the strict crossing when
      there is one, else the last recorded cycle for a cell that stopped at the
      criterion (within CRITERION_REACHED_MAX_AH), else NaN.
    * `cycle_life_basis`     -- which of those two applied, or "censored".

    `eol_cycle_sustained` additionally requires the sub-threshold run to last
    SUSTAIN cycles, which rejects a one-cycle dip; 2017-06-30 has a cluster of
    single-cycle capacity dips around cycle 250 from the computer restart, and a
    cell already near threshold could be pushed under by one. Where it and
    `eol_cycle_strict_lt` disagree the row is flagged, not silently resolved.
    """
    k = first_valid_index(qd)
    c, q = cycle[k:], qd[k:]
    below = np.isfinite(q) & (q < EOL)
    qd_last = float(qd[-1])
    res = {"eol_cycle_strict_lt": np.nan, "eol_cycle_sustained": np.nan,
           "n_leading_invalid_cycles": int(k),
           "reached_criterion": bool(qd_last <= matr.CRITERION_REACHED_MAX_AH),
           "cycle_life_cycles": np.nan, "cycle_life_basis": "censored"}
    if below.any():
        res["eol_cycle_strict_lt"] = float(c[int(np.argmax(below))])
        for i in np.flatnonzero(below):
            if below[i:i + SUSTAIN].all():
                res["eol_cycle_sustained"] = float(c[i])
                break
        res["cycle_life_cycles"] = res["eol_cycle_strict_lt"]
        res["cycle_life_basis"] = "strict_crossing_below_0.88Ah"
    elif res["reached_criterion"]:
        res["cycle_life_cycles"] = float(n_recorded)
        res["cycle_life_basis"] = "test_terminated_at_criterion"
    return res


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    meta = {d: matr.read_batch_metadata(d) for d in matr.BATCH_DATES}

    # ---- locate continuations by normalised barcode
    by_barcode: dict[str, list[matr.CellRecord]] = {}
    for d in matr.BATCH_DATES:
        for r in meta[d]:
            by_barcode.setdefault(r.barcode.upper(), []).append(r)
    for segs in by_barcode.values():
        segs.sort(key=lambda r: matr.BATCH_DATES.index(r.batch_date))

    rows = []
    for barcode, segs in by_barcode.items():
        first = segs[0]
        pol = matr.parse_policy(first.policy_readable)
        # A continued cell's 2017-06-30 policy string is truncated ("80%)-3.6C"),
        # so take the policy from the earliest segment, which is intact.
        issues = []
        for s in segs:
            issues += [f"[{s.batch_date} ch{s.channel}] {m}"
                       for m in ti.cell_issues(s.batch_date, s.channel)]

        # joined capacity series, in segment order (this is the only place
        # segments are concatenated, and only to compute a cycle life)
        cyc_parts, qd_parts, offset = [], [], 0.0
        for s in segs:
            cyc_parts.append(s.summary["cycle"] + offset)
            qd_parts.append(s.summary["QDischarge"])
            offset += len(s.summary["cycle"])
        cycle_j = np.concatenate(cyc_parts)
        qd_j = np.concatenate(qd_parts)
        n_rec = int(sum(s.n_cycles for s in segs))
        eol = eol_cycles(cycle_j, qd_j, n_rec)

        per_seg_eol = [eol_cycles(s.summary["cycle"], s.summary["QDischarge"],
                                  s.n_cycles)["cycle_life_cycles"] for s in segs]

        qd_valid = qd_j[first_valid_index(qd_j):]
        rows.append({
            "cell_uid": barcode,
            "barcode": barcode,
            "barcode_as_stored": " | ".join(s.barcode for s in segs),
            "n_segments": len(segs),
            "batch_date": first.batch_date,
            "channel": first.channel,
            "all_segments": " | ".join(f"{s.batch_date}:ch{s.channel}" for s in segs),
            "continued_in": segs[1].batch_date if len(segs) > 1 else "",
            "continued_channel": segs[1].channel if len(segs) > 1 else np.nan,
            "is_continuation": len(segs) > 1,
            "in_struct": True,
            "policy_readable": first.policy_readable,
            "policy_canonical": pol["canonical"],
            "policy_C1": pol["C1"], "policy_Q1_pct": pol["Q1"], "policy_C2": pol["C2"],
            "policy_n_steps": pol["n_steps"],
            "policy_suffix": pol["suffix"],
            "policy_string_intact": pol["parsed"],
            "policy_truncated_in_any_segment": any(
                (lambda q: not q["parsed"] or q["truncated_tail"])(
                    matr.parse_policy(s.policy_readable)) for s in segs),
            "policy_as_stored_all_segments": " | ".join(s.policy_readable for s in segs),
            "n_cycles_recorded": n_rec,
            "n_cycles_per_segment": " | ".join(str(s.n_cycles) for s in segs),
            "cycle_life_struct_field": segs[-1].cycle_life_field,
            "cycle_life_struct_field_all": " | ".join(
                ("nan" if np.isnan(s.cycle_life_field) else str(int(s.cycle_life_field)))
                for s in segs),
            "cycle_life_cycles": eol["cycle_life_cycles"],
            "cycle_life_basis": eol["cycle_life_basis"],
            "eol_cycle_strict_lt": eol["eol_cycle_strict_lt"],
            "eol_cycle_sustained": eol["eol_cycle_sustained"],
            "cycle_life_per_segment": " | ".join(
                ("nan" if np.isnan(v) else str(int(v))) for v in per_seg_eol),
            "eol_crossing_is_isolated_dip": bool(
                np.isfinite(eol["eol_cycle_strict_lt"])
                and not np.isfinite(eol["eol_cycle_sustained"])),
            "reached_criterion": eol["reached_criterion"],
            "censored": not eol["reached_criterion"] and not np.isfinite(eol["eol_cycle_strict_lt"]),
            "n_leading_invalid_cycles": eol["n_leading_invalid_cycles"],
            "QD_first_valid_Ah": float(qd_valid[0]) if qd_valid.size else np.nan,
            "QD_last_Ah": float(qd_j[-1]),
            "QD_min_Ah": float(np.nanmin(qd_valid)) if qd_valid.size else np.nan,
            "QD_max_Ah": float(np.nanmax(qd_valid)) if qd_valid.size else np.nan,
            "known_issues_cell": "; ".join(issues),
            "known_issues_batch": "; ".join(
                m for s in segs for m in ti.BATCH_ISSUES.get(s.batch_date, [])),
        })

    # ---- channels with no struct row at all
    missing = {}
    for d in matr.BATCH_DATES:
        present = {r.channel for r in meta[d]}
        missing[d] = sorted(set(ALL_CHANNELS) - present)
        for ch in missing[d]:
            rows.append({
                "cell_uid": f"{d}:ch{ch:02d}:NO_DATA",
                "barcode": "", "barcode_as_stored": "", "n_segments": 0,
                "batch_date": d, "channel": ch,
                "all_segments": f"{d}:ch{ch}",
                "continued_in": "", "continued_channel": np.nan,
                "is_continuation": False, "in_struct": False,
                "policy_readable": "", "policy_canonical": "",
                "policy_C1": np.nan, "policy_Q1_pct": np.nan, "policy_C2": np.nan,
                "policy_n_steps": np.nan, "policy_suffix": "",
                "policy_string_intact": False,
                "policy_truncated_in_any_segment": False,
                "policy_as_stored_all_segments": "",
                "n_cycles_recorded": 0, "n_cycles_per_segment": "",
                "cycle_life_struct_field": np.nan, "cycle_life_struct_field_all": "",
                "cycle_life_cycles": np.nan, "cycle_life_basis": "no_data",
                "eol_cycle_strict_lt": np.nan, "eol_cycle_sustained": np.nan,
                "cycle_life_per_segment": "",
                "eol_crossing_is_isolated_dip": False,
                "reached_criterion": False,
                "censored": False, "n_leading_invalid_cycles": 0,
                "QD_first_valid_Ah": np.nan, "QD_last_Ah": np.nan,
                "QD_min_Ah": np.nan, "QD_max_Ah": np.nan,
                "known_issues_cell": "; ".join(
                    f"[{d} ch{ch}] {m}" for m in ti.cell_issues(d, ch)) or
                    f"[{d} ch{ch}] no struct row; not mentioned on the batch page",
                "known_issues_batch": "; ".join(ti.BATCH_ISSUES.get(d, [])),
            })

    df = pd.DataFrame(rows)

    # ---- category, exactly one per physical cell
    def category(r):
        if not r["in_struct"]:
            return "no_data"
        if "possibly defective" in r["known_issues_cell"]:
            return "flagged_defective"
        if r["is_continuation"]:
            return "continued"
        if r["censored"]:
            return "censored"
        return "complete"

    df["category"] = df.apply(category, axis=1)
    df = df.sort_values(["batch_date", "channel"]).reset_index(drop=True)

    missing_df = pd.DataFrame(
        [{"batch_date": d, "n_struct_rows": len(meta[d]),
          "channels_present": len({r.channel for r in meta[d]}),
          "missing_channels": ", ".join(map(str, missing[d])) or "(none)"}
         for d in matr.BATCH_DATES])
    return df, missing_df


if __name__ == "__main__":
    df, missing_df = build()
    cols_first = ["cell_uid", "batch_date", "channel", "barcode", "policy_canonical",
                  "n_cycles_recorded", "cycle_life_cycles", "cycle_life_basis",
                  "censored", "is_continuation", "continued_in", "category",
                  "known_issues_cell"]
    df = df[cols_first + [c for c in df.columns if c not in cols_first]]
    df.to_csv(OUT_DIR / "cell_inventory.csv", index=False)
    print(f"wrote {OUT_DIR/'cell_inventory.csv'}  rows={len(df)}")

    print("\n### struct rows / missing channels")
    print(missing_df.to_string(index=False))

    print("\n### physical-cell categories")
    print(df["category"].value_counts().to_string())
    print(f"\ntotal rows                     : {len(df)}")
    print(f"physical cells with data       : {int(df['in_struct'].sum())}")
    print(f"channels with no data          : {int((~df['in_struct']).sum())}")
    print(f"struct rows accounted for      : {int(df['n_segments'].sum())}")

    print("\n### per batch (first segment's batch)")
    print(df.groupby("batch_date")["category"].value_counts().to_string())

    print("\n### continued cells")
    cc = df[df["is_continuation"]]
    print(cc[["barcode", "all_segments", "policy_canonical", "n_cycles_per_segment",
              "n_cycles_recorded", "cycle_life_per_segment",
              "cycle_life_cycles", "cycle_life_basis"]].to_string(index=False))

    print("\n### cycle_life_basis")
    print(df[df["in_struct"]]
          .groupby("batch_date")["cycle_life_basis"].value_counts().to_string())

    print("\n### censored (never reached its test's termination criterion)")
    cz = df[df["censored"] & df["in_struct"]]
    print(cz[["batch_date", "channel", "barcode", "policy_canonical",
              "n_cycles_recorded", "QD_last_Ah"]].to_string(index=False))

    print("\n### rows whose stored policy string is truncated in some segment")
    bad = df[df["in_struct"] & df["policy_truncated_in_any_segment"]]
    print(bad[["batch_date", "channel", "policy_canonical",
               "policy_as_stored_all_segments"]].to_string(index=False))

    print("\n### EOL crossing from an isolated dip")
    iso = df[df["eol_crossing_is_isolated_dip"]]
    print(iso[["batch_date", "channel", "eol_cycle_first_cross", "QD_last_Ah"]].to_string(index=False)
          if len(iso) else "  (none)")
