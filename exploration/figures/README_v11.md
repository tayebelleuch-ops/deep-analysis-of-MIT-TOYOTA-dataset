# Figures — v1.1 (the within-cycle audit)

Additive. The 11 v1.0 figures and their index (`README.md`) are untouched; these four
carry the `figv11_` prefix so the two sets never collide. Findings:
[`../REPORT_v1.1.md`](../REPORT_v1.1.md).

All four are drawn through `plotstyle.py`, so batch identity is colour and flag class is
colour **and** dash pattern — nothing is distinguishable by colour alone. Every trace is
as extracted: nothing is smoothed, masked or interpolated.

| figure | shows | finding |
|---|---|---|
| `figv11_01_flagged_cycle_traces.png` | raw V, I and Qd for one restart, one artifact and one junction cycle, each against a **series-valid** cycle of the same cell | §4.1 — restart cycles are confirmed by their own series (13/13), junction cycles are not (0/25) |
| `figv11_02_cell17_corrupt_run.png` | `EL150800453240`: cycle duration and sample count across its whole life, with the failing band shaded, plus cycle 40 against the first fully valid cycle (54) | **U15** — the corrupt run is cycles 1–53, not cycle 40 |
| `figv11_03_bloated_cells.png` | samples per cycle for 2018-04-12 ch 46 and 2017-05-12 ch 17 against their batch medians, log scale, plus each cell's longest cycle | **U16** — ch 46's bloat is episodic across its life; ch 17's is one early run |
| `figv11_04_qdlin_corruption.png` | the worst-affected cycle's `Qdlin` against a valid cycle of the same cell, and the distribution of the worst excursion over all 48 affected cycles | **U13** — the interpolated curve reaches ±4,030 Ah on a 1.1 Ah cell |

A note on `figv11_02`: the obvious reference cycle, 30, is **not** usable as a clean
baseline despite being `is_clean_cycle = True` in v1.0 — it carries a 48 h internal gap of
its own. The figure uses cycle 54, the first cycle that passes every series check. That
mistake is worth recording because it is exactly the trap U15 describes.
