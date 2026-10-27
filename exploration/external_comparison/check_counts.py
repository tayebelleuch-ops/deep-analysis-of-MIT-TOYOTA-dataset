import sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[2]   # repo root, two levels up
sys.path.insert(0, str(REPO / "exploration"))
import matr
meta = matr.read_all_metadata()
print("Repo B loops `for j in range(1, len(summary['cycle']))` and indexes cycles[str(j)].")
print("So len(summary['cycle']) must not exceed the number of cycle groups.\n")
mism = 0
for bn, date in enumerate(matr.BATCH_DATES, start=1):
    with matr.BatchCycles(date) as bc:
        for i, rec in enumerate(meta[date]):
            n_sum = len(rec.summary["cycle"])
            n_cyc = bc.n_cycles(i)
            if n_sum != n_cyc:
                mism += 1
                print(f"  MISMATCH b{bn}c{i}  {date} ch{rec.channel:02d}: "
                      f"len(summary)={n_sum}  n_cycle_groups={n_cyc}")
print(f"\ncells where the two disagree: {mism} of 140")
print("\nFeatures Repo B actually feeds the model: cycles[j]['I'], ['V'], ['T'] only")
print("(it drops SOH, charge_policy, Qc, Qd, Time before building X).")
print("It never touches Qdlin / Tdlin / discharge_dQdV, i.e. none of the")
print("voltage-domain DeltaQ(V) features the Severson paper is built on.")
