import sys; sys.path.insert(0, 'exploration')
import matr, numpy as np

meta = {d: matr.read_batch_metadata(d) for d in matr.BATCH_DATES}

print("### barcode uniqueness / overlap")
for d, recs in meta.items():
    bcs = [r.barcode for r in recs]
    print(f"{d}: n={len(bcs)} unique={len(set(bcs))} empty={sum(1 for b in bcs if not b)}")

b1 = {r.barcode: r for r in meta['2017-05-12']}
b2 = {r.barcode: r for r in meta['2017-06-30']}
b3 = {r.barcode: r for r in meta['2018-04-12']}
print("\n### overlaps")
print("05-12 & 06-30:", sorted(set(b1) & set(b2)))
print("05-12 & 04-12:", sorted(set(b1) & set(b3)))
print("06-30 & 04-12:", sorted(set(b2) & set(b3)))

print("\n### the barcode-matched continuation pairs")
for bc in sorted(set(b1) & set(b2)):
    a, b = b1[bc], b2[bc]
    print(f"  {bc}: 05-12 idx{a.index:>2} ch{a.channel:>2} {a.policy_readable:<16} ncyc={a.n_cycles:>5} cl={a.cycle_life_field:>7}"
          f"   ||  06-30 idx{b.index:>2} ch{b.channel:>2} {b.policy_readable!r:<14} ncyc={b.n_cycles:>5} cl={b.cycle_life_field}")

print("\n### what upstream Load Data.ipynb removes from batch2 (0-based idx 7,8,9,15,16)")
for i in (7, 8, 9, 15, 16):
    r = meta['2017-06-30'][i]
    print(f"  idx{i}: ch{r.channel:>2} {r.barcode} {r.policy_readable!r} ncyc={r.n_cycles}")

print("\n### what upstream removes from batch1 (0-based idx 8,10,12,13,22)")
for i in (8, 10, 12, 13, 22):
    r = meta['2017-05-12'][i]
    qd = r.summary['QDischarge']
    print(f"  idx{i}: ch{r.channel:>2} {r.barcode} {r.policy_readable:<16} ncyc={r.n_cycles} QD_end={qd[-1]:.4f} min_QD={np.min(qd[1:]):.4f}")

print("\n### transcript's batch1 'terminated early' channels 13,19,21,22,31 -> what the data says")
for r in meta['2017-05-12']:
    if r.channel in (13, 19, 21, 22, 31):
        qd = r.summary['QDischarge']
        print(f"  ch{r.channel:>2} idx{r.index:>2} {r.barcode} {r.policy_readable:<16} ncyc={r.n_cycles} QD_end={qd[-1]:.4f} reached_088={'YES' if qd[-1]<0.88 else 'NO'}")

print("\n### batch2 ch10 (transcript: EL150800460605 dies quickly)")
for r in meta['2017-06-30']:
    if r.channel == 10:
        qd = r.summary['QDischarge']
        print(f"  ch10 idx{r.index} {r.barcode} {r.policy_readable!r} ncyc={r.n_cycles} QD_end={qd[-1]:.4f}")
print("  cells with fewest cycles in 06-30:")
for r in sorted(meta['2017-06-30'], key=lambda r: r.n_cycles)[:5]:
    print(f"    ch{r.channel:>2} {r.barcode} ncyc={r.n_cycles} QD_end={r.summary['QDischarge'][-1]:.4f}")

print("\n### batch2 ch3 (transcript: EL150800460623 restart near EOL)")
for r in meta['2017-06-30']:
    if r.channel == 3:
        print(f"  ch3 idx{r.index} barcode={r.barcode} policy={r.policy_readable!r} ncyc={r.n_cycles}")
