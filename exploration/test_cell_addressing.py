"""Guard against the one mistake that silently corrupts every cell-level claim:
confusing a struct ROW POSITION with a CHANNEL NUMBER.

None of the three batch structs stores its rows in channel order (see
schema.md), yet upstream addresses cells positionally throughout -- `b1c8`,
`b3c37`, `batch2_idx = [8:10,16:17]`, `nind = [3, 40:41]`. Every channel number
quoted on the dataset pages therefore has to be resolved through the decoded
`channel_id` field, never inferred from a row's position.

Run it directly; there is no test runner in this repo:

    ../.venv/bin/python test_cell_addressing.py

Reads the three .mat files mode="r" and writes nothing.
"""
from __future__ import annotations

import sys

import matr
import transcript_issues
from build_analysis_set import PAPER_EXCLUDED
from plots_7_10 import SAMPLE

# Upstream's removal / stitching lists, verbatim from `Load Data.ipynb` and
# `LoadData.m`, as 0-based struct positions (`b1c8` -> index 8). The channels
# these resolve to are what the exploration code must be using.
UPSTREAM_POSITIONAL = {
    "2017-05-12": ([8, 10, 12, 13, 22], [19, 13, 21, 22, 31]),   # "do not reach 80%"
    "2017-06-30": ([7, 8, 9, 15, 16], [1, 2, 3, 5, 6]),          # continuation rows
    "2018-04-12": ([2, 23, 32, 37, 42, 43], [12, 33, 41, 46, 6, 7]),  # "noisy"
}

# eda_utils.despike names this cell "b1c18"; it is channel 17, and its cycle-40
# QDischarge is the largest capacity value anywhere in the dataset.
DESPIKE_CELL = ("2017-05-12", 18, 17, "EL150800453240")

failures: list[str] = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def main() -> int:
    meta = {d: matr.read_batch_metadata(d) for d in matr.BATCH_DATES}

    for d, recs in meta.items():
        by_pos = [r.channel for r in recs]
        by_chan = {r.channel: r for r in recs}

        # 1. channel_id decoded for every row, and unique within the batch
        check(len(by_chan) == len(recs),
              f"{d}: channel_id not unique across {len(recs)} rows")
        check(all(1 <= c <= 48 for c in by_pos),
              f"{d}: channel_id outside 1..48: {sorted(set(by_pos) - set(range(1, 49)))}")

        # 2. row position is NOT channel number -- the whole point of this file.
        #    Asserted positively: if a batch ever became ordered, the shortcut
        #    `index + 1 == channel` would start working by accident and this
        #    test is what notices.
        off = [i for i, c in enumerate(by_pos) if i + 1 != c]
        check(off, f"{d}: rows ARE in channel order; `index + 1 == channel` "
                   f"now holds for all {len(recs)} rows -- re-read schema.md "
                   f"before trusting any positional lookup")
        inv = [i for i in range(1, len(by_pos)) if by_pos[i] < by_pos[i - 1]]
        check(inv, f"{d}: channel sequence is monotonically ascending")
        print(f"{d}: {len(recs)} rows, {len(off)} with index+1 != channel, "
              f"first descent at index {inv[0]} (ch {by_pos[inv[0] - 1]} -> "
              f"ch {by_pos[inv[0]]})")

        # 3. upstream's positional lists resolve to the channels we assume
        pos, expected = UPSTREAM_POSITIONAL[d]
        got = [recs[i].channel for i in pos]
        check(got == expected,
              f"{d}: upstream positions {pos} resolve to {got}, not {expected}")

        # 4. barcodes are present and well formed (the only other cell key)
        check(all(len(r.barcode) == 14 for r in recs),
              f"{d}: barcode length != 14 on some row")
        check(len({r.barcode.upper() for r in recs}) == len(recs),
              f"{d}: barcodes not unique (case-insensitively) within batch")

    # 5. every channel NAMED anywhere in the exploration code exists in its
    #    batch and resolves to a row whose decoded channel_id matches.
    named: dict[str, set[int]] = {d: set() for d in matr.BATCH_DATES}
    for (d, ch) in transcript_issues.CELL_ISSUES:
        named[d].add(ch)
    for d, chans in PAPER_EXCLUDED.items():
        named[d] |= set(chans)
    for d, chans in SAMPLE.items():
        named[d] |= set(chans)
    named["2017-05-12"] |= {15, 16}        # checks.check_thermocouple_swap
    named["2017-06-30"] |= {15, 16}

    for d, chans in named.items():
        by_chan = {r.channel: r for r in meta[d]}
        for ch in sorted(chans):
            r = by_chan.get(ch)
            if r is None:
                # channels 4 and 8 of 2017-05-12 never started: the page names
                # them, the struct has no row. That absence is a finding, not a
                # lookup bug, and cell_inventory.csv carries it as in_struct=False.
                check((d, ch) in {("2017-05-12", 4), ("2017-05-12", 8)},
                      f"{d}: named channel {ch} is absent from the struct")
                continue
            check(r.channel == ch, f"{d}: lookup for channel {ch} returned {r.channel}")
        print(f"{d}: {len(chans)} named channels resolved")

    # 6. the despike cell, the one place a positional name leaked into prose
    d, pos, ch, barcode = DESPIKE_CELL
    r = meta[d][pos]
    check(r.channel == ch,
          f"{d} index {pos} is channel {r.channel}, not {ch}")
    check(r.barcode.upper() == barcode,
          f"{d} index {pos} barcode is {r.barcode}, not {barcode}")
    qd = r.summary["QDischarge"]
    check(abs(qd[39] - 2.8841) < 1e-3,
          f"{barcode} cycle 40 QDischarge is {qd[39]:.4f} Ah, expected ~2.8841")
    print(f"{d} index {pos} -> ch {r.channel} / {r.barcode}, "
          f"cycle 40 QD = {qd[39]:.4f} Ah")

    if failures:
        print(f"\nFAIL ({len(failures)}):")
        for f in failures:
            if f:
                print("  -", f)
        return 1
    print("\nOK: all cell addressing resolves through channel_id / barcode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
