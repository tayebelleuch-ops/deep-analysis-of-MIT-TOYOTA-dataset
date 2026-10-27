#!/usr/bin/env python3
"""Everything in USAGE.md, in one runnable script.

    python examples/quickstart.py

From a clone it needs no configuration: the loader finds exploration/ by itself.
Anywhere else it downloads the three CSVs once into ~/.cache/matr_clean, or reads a
folder you name:

    MATR_CLEAN_DATA_DIR=/path/to/folder python examples/quickstart.py
"""

from __future__ import annotations

import matr_clean as mc


def main() -> None:
    rule = "-" * 72

    # ------------------------------------------------------------------ 0
    print(rule)
    print("0. What the defaults do")
    print(rule)
    mc.describe()

    # ------------------------------------------------------------------ 1
    print()
    print(rule)
    print("1. The labels")
    print(rule)
    labels = mc.load_labels()
    print("{0} labelled cells, held-out cells excluded".format(len(labels)))
    print(
        labels[
            ["cell_uid", "batch_date", "policy_canonical", "cycle_life_cycles", "eol_basis"]
        ]
        .head()
        .to_string(index=False)
    )
    print()
    print("cycle life, cycles:")
    print(labels["cycle_life_cycles"].describe()[["min", "50%", "max"]].to_string())
    print()
    print("how each label was obtained:")
    print(labels["eol_basis"].value_counts().to_string())

    # ------------------------------------------------------------------ 2
    print()
    print(rule)
    print("2. The trajectories")
    print(rule)
    cells, cycles = mc.load_trajectories()
    print("{0} cells, {1:,} clean cycles".format(len(cells), len(cycles)))
    print(
        cycles[["cell_uid", "cycle", "QD_Ah", "soh", "cycles_to_eol"]]
        .head()
        .to_string(index=False)
    )
    print()
    print("what load_trajectories() left out:")
    for line in cells.attrs["filters"]["excluded"]:
        print("  - {0}".format(line))

    # ------------------------------------------------------------------ 3
    print()
    print(rule)
    print("3. Fold cross-validation (new cells, batches and policies already seen)")
    print(rule)
    for split in mc.cv_splits("fold"):
        train = cycles[cycles["cell_uid"].isin(split.train)]
        test = cycles[cycles["cell_uid"].isin(split.test)]
        print(
            "  fold {0}: {1:>3} train cells / {2:>2} test cells"
            "   {3:>6,} / {4:>6,} cycles".format(
                split.label, split.n_train, split.n_test, len(train), len(test)
            )
        )

    # ------------------------------------------------------------------ 4
    print()
    print(rule)
    print("4. Leave one batch out, and leave one policy out")
    print(rule)
    for split in mc.cv_splits("batch"):
        held = cells.loc[cells["cell_uid"].isin(split.test)]
        print(
            "  hold out {0}: {1:>3} train cells, {2:>2} test cells,"
            " median target {3:.0f} cycles".format(
                split.label,
                split.n_train,
                split.n_test,
                held["eol_cycle_80pct_soh"].median(),
            )
        )
    policy_splits = list(mc.cv_splits("policy"))
    print()
    print("  leave-one-policy-out: {0} splits; the first three are".format(
        len(policy_splits)))
    for split in policy_splits[:3]:
        print("    {0:<16} {1:>2} cell(s) held out".format(split.label, split.n_test))

    # ------------------------------------------------------------------ 5
    print()
    print(rule)
    print("5. The held-out test cells, once")
    print(rule)
    print("  load_cells()                     {0:>3} cells (inventory view)".format(
        len(mc.load_cells())))
    print("  load_labels()                    {0:>3} cells".format(len(mc.load_labels())))
    print("  load_labels(include_test=True)   {0:>3} cells".format(
        len(mc.load_labels(include_test=True))))
    final = mc.load_trajectories(include_test=True)
    print("  load_trajectories(include_test=True)  {0:>3} cells, {1:,} cycles".format(
        len(final.cells), len(final.cycles)))
    with_test = list(mc.cv_splits("fold", include_test=True))
    print("  cv_splits('fold', include_test=True) -> labels {0}".format(
        [s.label for s in with_test]))
    print()
    print("  filters recorded on the last frame:")
    for key, value in sorted(final.cells.attrs["filters"].items()):
        if key != "excluded":
            print("    {0}: {1}".format(key, value))


if __name__ == "__main__":
    main()
