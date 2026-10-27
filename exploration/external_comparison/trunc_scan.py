"""How much of each within-cycle I/V/T series does Repo B's 1000-sample cap discard?
Probes 3 points in each cell's life (10%, 50%, 90%)."""
import sys
from pathlib import Path
import os, pathlib
import os, pathlib
import numpy as np, pandas as pd
REPO = Path(__file__).resolve().parents[2]   # repo root, two levels up
sys.path.insert(0, str(REPO / "exploration"))
import matr
import pathlib
OUT = pathlib.Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

rows=[]
for bn, date in enumerate(matr.BATCH_DATES, start=1):
    with matr.BatchCycles(date) as bc:
        for i in range(bc.n_cells):
            n = bc.n_cycles(i)
            if n < 10: continue
            for frac, tag in ((0.10,"early"), (0.50,"mid"), (0.90,"late")):
                j = max(1, min(n-1, int(n*frac)))
                L = len(bc.cycle(i, j, fields=("I",))["I"])
                rows.append(dict(key=f"b{bn}c{i}", batch=date, tag=tag,
                                 n_cycles=n, cycle=j, length=L,
                                 over=L>1000, pct_cut=max(0,(L-1000))/L*100))
df=pd.DataFrame(rows)
df.to_csv(str(OUT / "trunc_scan.csv"), index=False)
print("probed", len(df), "cycles across", df.key.nunique(), "cells\n")
piv = df.pivot_table(index="batch", columns="tag", values="pct_cut",
                     aggfunc="mean")[["early","mid","late"]]
print("mean % of each cycle's samples DISCARDED by the 1000-point cap:")
print(piv.round(1).to_string())
print()
piv2 = df.pivot_table(index="batch", columns="tag", values="over",
                      aggfunc="mean")[["early","mid","late"]]*100
print("% of probed cycles that exceed 1000 samples (i.e. get cut at all):")
print(piv2.round(0).to_string())
print()
print("overall:", f"{df.over.mean()*100:.0f}% of probed cycles are truncated;",
      f"mean discard {df.pct_cut.mean():.1f}% of the series")
print()
print("by position in life (all batches):")
print(df.groupby("tag").pct_cut.mean().reindex(["early","mid","late"]).round(1).to_string())
