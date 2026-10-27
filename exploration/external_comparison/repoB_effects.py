"""Quantify the downstream effect of Repo B's three data choices:
   (a) SOH normalised to QD[1] on already-aged continuation segments
   (b) savgol_filter(SOH, 90, 2) over cells containing capacity artifacts
   (c) truncation of within-cycle I/V/T series to the first 1000 samples
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import signal

REPO = Path(__file__).resolve().parents[2]   # repo root, two levels up
sys.path.insert(0, str(REPO / "exploration"))
import matr

meta = matr.read_all_metadata()
keyed = {}
for bn, date in enumerate(matr.BATCH_DATES, start=1):
    for i, rec in enumerate(meta[date]):
        keyed[f"b{bn}c{i}"] = rec

inv = pd.read_csv(REPO / "exploration" / "cell_inventory.csv")
chan2key = {(r.batch_date, r.channel): k for k, r in
            ((k, r) for k, r in keyed.items())}
chan2key = {(r.batch_date, r.channel): k for k, r in keyed.items()}

print("="*78)
print("(a) SOH normalised to an already-aged capacity: the 5 continuation 2nd segments")
print("="*78)
pairs = [("b1c0","b2c7"), ("b1c1","b2c8"), ("b1c2","b2c9"),
         ("b1c3","b2c15"), ("b1c4","b2c16")]
rows=[]
for k1,k2 in pairs:
    r1,r2 = keyed[k1], keyed[k2]
    q1 = r1.summary["QDischarge"]; q2 = r2.summary["QDischarge"]
    true_init = q1[1]            # beginning-of-life capacity, 1st segment
    their_init = q2[1]           # what Repo B divides the 2nd segment by
    rows.append(dict(barcode=r1.barcode.lower(), seg1=k1, seg2=k2,
        true_BoL_Ah=true_init, repoB_denom_Ah=their_init,
        repoB_SOH_at_seg2_start=1.0,
        true_SOH_at_seg2_start=their_init/true_init,
        repoB_final_SOH=q2[-1]/their_init,
        true_final_SOH=q2[-1]/true_init))
d=pd.DataFrame(rows)
pd.set_option("display.width",200)
print(d.to_string(index=False, float_format=lambda x:f"{x:.4f}"))
print(f"\nSOH overstated at the start of segment 2 by "
      f"{(1-d.true_SOH_at_seg2_start).min()*100:.1f}-{(1-d.true_SOH_at_seg2_start).max()*100:.1f} "
      f"percentage points; at the end by "
      f"{(d.repoB_final_SOH-d.true_final_SOH).min()*100:.1f}-"
      f"{(d.repoB_final_SOH-d.true_final_SOH).max()*100:.1f} pp.")
print("These 5 cells are TARGETS (y), so the error is in the label, not a feature.")

print()
print("="*78)
print("(b) savgol_filter(SOH, window=90, polyorder=2) over capacity artifacts")
print("="*78)
# cells our audit flags with physically impossible QD
bad = inv[inv.QD_max_Ah > 1.15][["cell_uid","batch_date","channel","QD_max_Ah"]]
print("cells whose summary QDischarge exceeds 1.15 Ah (physically impossible):")
for _,c in bad.iterrows():
    k = chan2key.get((c.batch_date, c.channel))
    print(f"  {c.cell_uid}  {c.batch_date} ch{c.channel:02d}  "
          f"QD_max={c.QD_max_Ah:.3f} Ah  -> Repo B key {k}")

print("\neffect of the 90-wide smoother on one of them:")
for _,c in bad.iterrows():
    k = chan2key.get((c.batch_date, c.channel))
    if k is None: continue
    rec = keyed[k]; q = rec.summary["QDischarge"]
    soh = q[1:]/q[1]
    sm = signal.savgol_filter(soh, 90, 2)
    j = int(np.argmax(soh))
    lo, hi = max(0,j-60), min(len(soh), j+61)
    # how far from the local trend does the smoothed curve get pulled?
    pull = sm[lo:hi] - np.median(soh[lo:hi])
    print(f"  {k} ({c.batch_date} ch{c.channel}): spike at cycle {j+1}, "
          f"raw SOH={soh[j]:.3f}; smoothed curve displaced up to "
          f"{np.abs(pull).max()*100:.1f} SOH-points over a "
          f"{int(np.sum(np.abs(sm-np.median(soh[lo:hi]))>0.01))}-cycle span")

mins = [len(keyed[k].summary['QDischarge'])-1 for k in keyed]
print(f"\nshortest cell record = {min(mins)} cycles; "
      f"cells shorter than the 90-cycle window = {sum(1 for m in mins if m<90)}")

print()
print("="*78)
print("(c) within-cycle series truncated to the first 1000 samples")
print("="*78)
# sample cycles across life for a few representative cells
for date, ci, label in [("2017-05-12", 6, "2017-05-12 mid-life cell"),
                        ("2017-06-30", 20, "2017-06-30 cell"),
                        ("2018-04-12", 20, "2018-04-12 cell")]:
    with matr.BatchCycles(date) as bc:
        n = bc.n_cycles(ci)
        probes = [1, n//4, n//2, 3*n//4, n-1]
        lens=[]
        for j in probes:
            cyc = bc.cycle(ci, j, fields=("I",))
            lens.append(len(cyc["I"]))
        frac_cut=[max(0,(L-1000))/L*100 for L in lens]
        print(f"{label} (struct row {ci}, {n} cycles)")
        print(f"   cycle      : {probes}")
        print(f"   len(I)     : {lens}")
        print(f"   % discarded: {[f'{f:.0f}%' for f in frac_cut]}")
