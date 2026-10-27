import sys; sys.path.insert(0,'exploration')
import matr, numpy as np

REST = 0.01  # |I| below this (C-rate) counts as rest/open-circuit

def runs(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]: j += 1
            out.append((i, j-1)); i = j
        else: i += 1
    return out

for d in matr.BATCH_DATES:
    print("="*70); print(d)
    with matr.BatchCycles(d) as bc:
        n = bc.n_cycles(0)
        for ci in [0, 1, 2, 50, n-2, n-1]:
            if ci < 0 or ci >= n: continue
            c = bc.cycle(0, ci, ("t","I","V","Qc","Qd"))
            t, I, V = c["t"], c["I"], c["V"]
            if t.size < 5:
                print(f"  idx{ci:>5}: placeholder (len {t.size})"); continue
            chg = I > REST; dis = I < -REST; rest = np.abs(I) <= REST
            min_pos = np.nanmin(I[chg]) if chg.any() else np.nan
            # rest runs, in seconds
            rr = [(t[b]-t[a])*60 for a,b in runs(rest) if b > a]
            rr = [round(x,1) for x in rr if x > 0.2]
            # CV tail = charge samples where V is within 1 mV of its max
            vmax = np.nanmax(V[chg]) if chg.any() else np.nan
            cv = chg & (V > vmax - 0.001)
            cv_min = (t[cv].max()-t[cv].min()) if cv.sum() > 1 else 0.0
            chg_min = (t[chg].max()-t[chg].min()) if chg.sum() > 1 else 0.0
            print(f"  idx{ci:>5}: dur={t[-1]:6.2f}min n={t.size:>5} "
                  f"|I|max={np.nanmax(np.abs(I)):5.3f} Imax_chg={np.nanmax(I[chg]) if chg.any() else np.nan:5.3f} "
                  f"Imin_chg={min_pos:7.4f} Vmax={vmax:6.4f} "
                  f"chg={chg_min:5.2f}min CVtail={cv_min:5.2f}min rests_s={rr[:6]}")
