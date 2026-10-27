"""Reproduce Repo B's (Energetic-project-2) cell set and SOH definition from the
raw .mat files, and compare against exploration/analysis_set_cells.csv."""
import sys
from pathlib import Path
import os, pathlib
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]   # repo root, two levels up
sys.path.insert(0, str(REPO / "exploration"))
import matr
import pathlib
OUT = pathlib.Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# ---- Repo B's key order: struct row order, b1c0..b1c45, b2c0..b2c47, b3c0..b3c45
meta = matr.read_all_metadata()
rows = []
for bn, date in enumerate(matr.BATCH_DATES, start=1):
    for i, rec in enumerate(meta[date]):
        rows.append(dict(repoB_key=f"b{bn}c{i}", batch_date=date,
                         struct_row=i, channel=rec.channel,
                         barcode=rec.barcode.lower() if rec.barcode else None,
                         QD=rec.summary["QDischarge"]))
print(f"struct rows total = {len(rows)}")

inv = pd.read_csv(REPO / "exploration" / "cell_inventory.csv")

out = []
for r in rows:
    QD = r["QD"]
    n = len(QD)
    # Repo B: for j in range(1, len(summary['cycle'])), SOH = QD[j]/QD[1]
    init = QD[1]
    soh = QD[1:n] / init
    out.append(dict(repoB_key=r["repoB_key"], batch_date=r["batch_date"],
                    channel=r["channel"], barcode=r["barcode"],
                    n_cycles_rowB=n - 1,
                    QD1_Ah=init, QD_last_Ah=QD[-1],
                    soh_min=soh.min(), soh_final=soh[-1],
                    reaches_80=bool(soh.min() < 0.80)))
b = pd.DataFrame(out)

print("\n=== Repo B cell set ===")
print(f"all struct rows kept by their loader : {len(b)}")
print("their notebook then does cells=cells[1:] -> drops the first list entry:")
print(b.iloc[0][["repoB_key", "batch_date", "channel", "barcode", "n_cycles_rowB"]].to_string())
bk = b.iloc[1:].copy()
print(f"\nmodelled cells = {len(bk)}  (notebook printed len(cells)=139)")

print("\n=== Their SOH denominator: QD[cycle index 1], per cell ===")
print(f"QD[1] range          : {b.QD1_Ah.min():.4f} - {b.QD1_Ah.max():.4f} Ah")
print(f"QD[1] median         : {b.QD1_Ah.median():.4f} Ah")
print(f"nominal              : 1.1000 Ah -> 0.88 Ah = 80% of nominal")
print(f"0.88 Ah as % of QD[1]: {(0.88/b.QD1_Ah*100).min():.1f}% - {(0.88/b.QD1_Ah*100).max():.1f}%")

print("\n=== Do their cells reach 'End Of Life' = SOH 0.80 under their own definition? ===")
print(f"reach SOH<0.80 : {int(bk.reaches_80.sum())} of {len(bk)}")
print(f"never reach it : {int((~bk.reaches_80).sum())} of {len(bk)}")
print("\nby batch:")
print(bk.groupby("batch_date").reaches_80.agg(["sum", "count"]))
print("\nfinal SOH (their definition) by batch:")
print(bk.groupby("batch_date").soh_final.describe()[["min", "50%", "max"]])

# ---- duplicate physical cells (continuations) under their keying
print("\n=== Physical-cell duplication (the 5 continued cells) ===")
cont = inv[inv.is_continuation == True]
dups = b[b.barcode.notna()].groupby("barcode").repoB_key.apply(list)
dups = dups[dups.apply(len) > 1]
print(f"barcodes appearing under 2 repo-B keys: {len(dups)}")
for bc, keys in dups.items():
    seg = b[b.barcode == bc][["repoB_key", "batch_date", "channel", "n_cycles_rowB"]]
    print(f"  {bc}: {keys}")
    print(seg.to_string(index=False))
print(f"\n-> {len(dups)} physical cells each enter their 139 TWICE as independent 'cells'.")
print("   random.shuffle + 60/40 split can place the two halves of one physical")
print("   cell on opposite sides of the train/test boundary.")

# ---- censored cells present?
print("\n=== Censored cells (never reached any criterion) ===")
cens = inv[inv.censored == True][["cell_uid", "batch_date", "channel", "QD_last_Ah"]]
print(cens.to_string(index=False))
cens_keys = []
for _, c in cens.iterrows():
    m = b[(b.batch_date == c.batch_date) & (b.channel == c.channel)]
    if len(m):
        cens_keys.append(m.iloc[0].repoB_key)
print(f"present in their 139 as: {cens_keys}")

# ---- comparison table
ours = pd.read_csv(REPO / "exploration" / "analysis_set_cells.csv")
print("\n=== Head-to-head ===")
print(f"{'quantity':42s} {'Repo B':>12s} {'this repo':>12s}")
def line(k, x, y): print(f"{k:42s} {x:>12} {y:>12}")
line("struct rows read", 140, 140)
line("physical cells resolved", "not done", len(ours))
line("cells entering the model", len(bk), int(ours.use_for_trajectory.sum()))
line("cells with an EOL label", int(bk.reaches_80.sum()), int(ours.has_eol_label.sum()))
line("duplicate physical cells", len(dups) * 2, 0)
line("censored cells kept unlabelled", 0, int(ours.censored.sum()))
line("SOH denominator", "QD[1]/cell", "1.1 Ah nominal")
b.to_csv(str(OUT / "repoB_cells.csv"), index=False)
