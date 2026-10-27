"""Isolate what the 90-wide Savitzky-Golay smoother does to the capacity artifacts,
by comparing savgol(raw SOH) against savgol(despiked SOH)."""
import sys
from pathlib import Path
import os, pathlib
import os, pathlib
import numpy as np, pandas as pd
from scipy import signal

REPO = Path(__file__).resolve().parents[2]   # repo root, two levels up
sys.path.insert(0, str(REPO / "exploration"))
import matr
import pathlib
OUT = pathlib.Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

meta = matr.read_all_metadata()
keyed = {}
for bn, date in enumerate(matr.BATCH_DATES, start=1):
    for i, rec in enumerate(meta[date]):
        keyed[f"b{bn}c{i}"] = rec

def despike(y, thresh=0.03):
    """Replace isolated single-cycle outliers by the local median."""
    y = y.copy()
    med = signal.medfilt(y, 5)
    bad = np.abs(y - med) > thresh
    y[bad] = med[bad]
    return y, bad

print(f"{'key':7s} {'batch / ch':22s} {'n_art':>5s} {'max|savgol(raw)-savgol(clean)|':>31s} {'cycles>0.005':>13s}")
print("-"*86)
rows=[]
for k, rec in keyed.items():
    q = rec.summary["QDischarge"]
    soh = q[1:]/q[1]
    if len(soh) < 95: continue
    clean, bad = despike(soh)
    a = signal.savgol_filter(soh, 90, 2)
    b = signal.savgol_filter(clean, 90, 2)
    d = np.abs(a-b)
    rows.append(dict(key=k, batch=rec.batch_date, ch=rec.channel,
                     n_art=int(bad.sum()), max_disp=d.max(),
                     n_affected=int((d>0.005).sum()), n=len(soh)))
df = pd.DataFrame(rows)
top = df.nlargest(12, "max_disp")
for _,r in top.iterrows():
    print(f"{r.key:7s} {r.batch+' ch'+str(r.ch):22s} {r.n_art:5d} "
          f"{r.max_disp*100:>29.1f}pp {r.n_affected:13d}")

print()
print(f"cells modelled by Repo B with >=1 detected artifact : "
      f"{int((df.n_art>0).sum())} of {len(df)}")
print(f"cells where smoothing the artifact displaces SOH by >1pp : "
      f"{int((df.max_disp>0.01).sum())}")
print(f"cells where it displaces SOH by >0.5pp : {int((df.max_disp>0.005).sum())}")
print(f"median cycles per cell whose smoothed SOH moves >0.5pp : "
      f"{int(df[df.n_affected>0].n_affected.median())}")
print()
print("For reference the whole target range is SOH 1.00 -> 0.80, i.e. 20 pp,")
print("so a 4 pp displacement is ~20% of the full dynamic range of the label.")
df.to_csv(str(OUT / "savgol_effect.csv"), index=False)
