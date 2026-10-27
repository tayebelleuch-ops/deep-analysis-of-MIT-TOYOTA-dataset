import os
"""Re-verify every headline number asserted in comparison_external_repos.md."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.io import loadmat
REPO = Path(__file__).resolve().parents[2]   # repo root, two levels up
sys.path.insert(0, str(REPO / "exploration"))
import matr

ok = lambda c, m: print(("  PASS  " if c else "  FAIL  ") + m)

meta = matr.read_all_metadata()
keyed = {f"b{bn}c{i}": r for bn, d in enumerate(matr.BATCH_DATES, 1)
         for i, r in enumerate(meta[d])}
print("MATR / Repo B")
ok(len(keyed) == 140, "140 struct rows in the three .mat files")
ok(len(keyed) - 1 == 139, "Repo B's cells[1:] leaves 139")

# b1c0 identity
r = keyed["b1c0"]
ok(r.barcode.lower() == "el150800460514" and r.channel == 1,
   "the row cells[1:] drops is b1c0 = EL150800460514, 2017-05-12 ch 1")

# duplicates
bc = {}
for k, rec in keyed.items():
    bc.setdefault(rec.barcode.lower(), []).append(k)
dups = {b: v for b, v in bc.items() if len(v) > 1}
ok(len(dups) == 5, f"5 barcodes appear twice ({len(dups)} found)")
ok(set(sum(dups.values(), [])) ==
   {"b1c0","b1c1","b1c2","b1c3","b1c4","b2c7","b2c8","b2c9","b2c15","b2c16"},
   "and they are b1c0-b1c4 paired with b2c7/8/9/15/16")

# SOH / EOL under Repo B's formula
rows = []
for k, rec in keyed.items():
    q = rec.summary["QDischarge"]
    rows.append(dict(key=k, batch=rec.batch_date, soh_min=(q[1:]/q[1]).min()))
b = pd.DataFrame(rows).set_index("key").drop(index="b1c0")
reach = b.soh_min < 0.80
ok(len(b) == 139, "139 modelled rows")
ok(int(reach.sum()) == 43, f"43 of 139 reach SOH<0.80 ({int(reach.sum())})")
ok(int((~reach).sum()) == 96, f"96 never reach it ({int((~reach).sum())})")
by = b.assign(r=reach).groupby("batch").r.agg(["sum","count"])
ok(by.loc["2017-05-12","sum"] == 0 and by.loc["2017-05-12","count"] == 45,
   "2017-05-12: 0 of 45")
ok(by.loc["2017-06-30","sum"] == 43 and by.loc["2017-06-30","count"] == 48,
   "2017-06-30: 43 of 48")
ok(by.loc["2018-04-12","sum"] == 0 and by.loc["2018-04-12","count"] == 46,
   "2018-04-12: 0 of 46")

# the 5 failing batch-2 rows are the continuations
f = set(b[(b.batch == "2017-06-30") & (~reach)].index)
ok(f == {"b2c7","b2c8","b2c9","b2c15","b2c16"},
   "the 5 batch-2 rows failing to reach EOL are exactly the continuations")

# our analysis set
o = pd.read_csv(REPO/"exploration"/"analysis_set_cells.csv")
ok(len(o) == 135, "our set: 135 physical cells")
ok(int(o.has_eol_label.sum()) == 128, "128 labelled")
ok(int(o.use_for_trajectory.sum()) == 130, "130 in the default trajectory set")
ok(int((o.use_for_trajectory & o.has_eol_label).sum()) == 123, "123 of those labelled")
ok(int(o.in_paper_124.sum()) == 124, "in_paper_124 sums to 124")
ok(int(o.censored.sum()) == 7, "7 censored")
inv = pd.read_csv(REPO/"exploration"/"cell_inventory.csv")
ok(len(inv[(inv.batch_date=="2017-06-30")]) == 43 and
   int(inv[inv.batch_date=="2017-06-30"].is_continuation.sum()) == 0,
   "our 2017-06-30 holds exactly 43 non-continuation physical cells (same 43)")

# U6
q = keyed["b1c18"].summary["QDischarge"]
j = int(np.argmax(q))
ok(abs(q[j] - 2.8841) < 1e-3 and keyed["b1c18"].summary["cycle"][j] == 40,
   f"b1c18 peaks at {q[j]:.4f} Ah at cycle 40, NOT 1.81 Ah (REPORT.md U6 error)")
ok(abs(q[j]/1.1 - 2.62) < 0.01, f"that is {q[j]/1.1:.2f}x nominal")

print("\nISEA / Repo A")
m = loadmat(os.environ.get("ISEA_MAT", "/tmp/isea/Degradation_Prediction_Dataset_ISEA.mat"),
            squeeze_me=True, struct_as_record=False)["TDS"]
cells = np.array([r.Cell for r in m])
ok(len(m) == 10686, f"10,686 samples ({len(m)})")
ok(len(np.unique(cells)) == 47, f"47 distinct cells ({len(np.unique(cells))}), README says 48")
cap = np.concatenate([np.atleast_1d(r.History).ravel() for r in m])
cap = cap[cap > 0]
ok(1.82 < cap.max() < 1.86, f"capacities top out at {cap.max():.4f} Ah (not 1.1)")
firsts, lasts = [], []
for c in np.unique(cells):
    rs = [r for r in m if r.Cell == c]
    h = np.atleast_1d(rs[0].History).ravel()
    tg = np.concatenate([np.atleast_1d(r.Target_expanded).ravel() for r in rs])
    firsts.append(h[0]); lasts.append(tg[tg > 0].min())
firsts, lasts = np.array(firsts), np.array(lasts)
soh = lasts/firsts
ok((soh < 0.80).all(), f"all 47 cells cross 80% of their own initial ({int((soh<0.80).sum())}/47)")
ok(0.45 < soh.min() < 0.47 and 0.46 < soh.max() < 0.47,
   f"final SOH vs own initial: {soh.min():.3f}-{soh.max():.3f}")
te = [15,20,25,30,35]
n_te = sum(1 for r in m if r.Cell in te)
ok(n_te == 1083, f"held-out cells carry {n_te} samples (10.1%)")
print("\ndone")
