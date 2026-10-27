import os
"""Inspect the ISEA (RWTH) Degradation_Prediction_Dataset_ISEA.mat TDS struct."""
import numpy as np
from scipy.io import loadmat

P = os.environ.get("ISEA_MAT", "/tmp/isea/Degradation_Prediction_Dataset_ISEA.mat")
m = loadmat(P, squeeze_me=True, struct_as_record=False)
keys = [k for k in m if not k.startswith("__")]
print("top-level variables:", keys)
TDS = m["TDS"]
print("TDS rows (samples):", len(TDS))
f = [a for a in dir(TDS[0]) if not a.startswith("_")]
print("fields:", f)

cells = np.array([r.Cell for r in TDS])
uniq = np.unique(cells)
print(f"\ndistinct cells: {len(uniq)}  -> {uniq}")
print(f"samples per cell: min {np.bincount(cells)[uniq].min()}, "
      f"max {np.bincount(cells)[uniq].max()}, "
      f"median {int(np.median(np.bincount(cells)[uniq]))}")

# capacity range across all history+target
allcap = np.concatenate([np.atleast_1d(r.History).ravel() for r in TDS] +
                        [np.atleast_1d(r.Target).ravel() for r in TDS])
allcap = allcap[allcap > 0]
print(f"\ncapacity values (Ah): min {allcap.min():.4f}  max {allcap.max():.4f}")
print(f"  -> suggests a nominal capacity near {allcap.max():.2f} Ah "
      f"(MATR cells are 1.1 Ah)")

# per cell: first and last capacity, and max cycle reached
print(f"\n{'cell':>5s} {'n_samp':>7s} {'cap_first':>10s} {'cap_last':>9s} "
      f"{'SOH_last':>9s} {'max_cycle':>10s}")
rows=[]
for c in uniq:
    rs = [r for r in TDS if r.Cell == c]
    hist0 = np.atleast_1d(rs[0].History).ravel()
    # last target of the sample with the largest final cycle
    lastcyc = max(np.atleast_1d(r.Target_Cycle_Expanded).ravel().max() for r in rs)
    tg = np.concatenate([np.atleast_1d(r.Target_expanded).ravel() for r in rs])
    tg = tg[tg > 0]
    rows.append((c, len(rs), hist0[0], tg.min(), tg.min()/hist0[0], lastcyc))
for r in rows[:10]:
    print(f"{r[0]:5d} {r[1]:7d} {r[2]:10.4f} {r[3]:9.4f} {r[4]:9.4f} {r[5]:10.0f}")
print(f"... ({len(rows)} cells total)")

arr = np.array([(r[2], r[3], r[4], r[5]) for r in rows])
print(f"\nacross cells:")
print(f"  initial capacity : {arr[:,0].min():.4f} - {arr[:,0].max():.4f} Ah")
print(f"  final capacity   : {arr[:,1].min():.4f} - {arr[:,1].max():.4f} Ah")
print(f"  final SOH (vs own first value): {arr[:,2].min():.3f} - {arr[:,2].max():.3f}")
print(f"  longest cycle reached: {arr[:,3].min():.0f} - {arr[:,3].max():.0f}")
nb80 = int((arr[:,2] < 0.80).sum())
print(f"  cells whose capacity falls below 80% of their own first value: {nb80} of {len(rows)}")

# history / target lengths -> the padding the MATLAB script computes
hl = [len(np.atleast_1d(r.History).ravel()) for r in TDS]
tl = [len(np.atleast_1d(r.Target).ravel()) for r in TDS]
print(f"\nHistory length : {min(hl)} - {max(hl)} (5-cycle spacing)")
print(f"Target  length : {min(tl)} - {max(tl)} (50-cycle spacing)")

# the held-out test cells named in the MATLAB script
test_cells=[15,20,25,30,35]
present=[c for c in test_cells if c in uniq]
n_te=sum(1 for r in TDS if r.Cell in test_cells)
print(f"\nMATLAB script holds out cells {test_cells}; present in TDS: {present}")
print(f"test samples {n_te} of {len(TDS)} = {n_te/len(TDS)*100:.1f}%  "
      f"({len(present)} of {len(uniq)} cells = {len(present)/len(uniq)*100:.1f}%)")
