"""Known issues transcribed from the four dataset pages in claude_dropzone/.

Kept as data, separate from any measurement, so that Step 2 can compare
"what the page claims" against "what the file contains" without the two
being tangled. Channel numbers are as printed on the pages.
"""

# Issues the pages attribute to a specific channel within a batch.
CELL_ISSUES: dict[tuple[str, int], list[str]] = {}

def _add(batch_date, channels, note):
    for ch in channels:
        CELL_ISSUES.setdefault((batch_date, ch), []).append(note)

# ---- 2017-05-12 (page 02)
_add("2017-05-12", [4, 8], "page: test did not successfully start, no data")
_add("2017-05-12", [13, 19, 21, 22, 31], "page: terminated before reaching 80% of nominal capacity")
_add("2017-05-12", [15, 16], "page: thermocouples accidentally switched (with each other)")
_add("2017-05-12", [1, 2, 3, 5, 6], "page: stopped at end of batch and resumed in 2017-06-30")

# ---- 2017-06-30 (page 03)
_add("2017-06-30", [1, 2, 3, 5, 6], "page: continuation of a 2017-05-12 cell (link on barcode), NOT a new experiment")
_add("2017-06-30", [3], "page: second computer restart near end of test, expect capacity spike near EOL")
_add("2017-06-30", [10], "page: dies quickly, possibly defective (no obvious signs found)")
_add("2017-06-30", [7, 21], "page: thermocouple had fallen off the cell (found on unloading)")
_add("2017-06-30", [15, 16], "page: thermocouples accidentally switched (with each other)")

# ---- 2018-04-12 (page 04)
_add("2018-04-12", [33, 41], "page: terminated before reaching 80% of nominal capacity")
_add("2018-04-12", [46], "page: noisy voltage profiles, likely electronic connection error")

# Issues the pages attribute to the whole batch.
BATCH_ISSUES: dict[str, list[str]] = {
    "2017-05-12": [
        "page: computer automatically restarted twice -> time gaps in data",
        "page: temperature control somewhat inconsistent -> variable baseline chamber temperature",
        "page: cycle 1 excluded from struct (sampling rate too high)",
    ],
    "2017-06-30": [
        "page: computer restart affecting all tests around cycle 250 -> ~8 h rest, capacity spikes",
    ],
    "2018-04-12": [
        "page: some cells had OCV errors from the IR test -> temporary pauses in cycling (cells not identified)",
    ],
}

# Experimental-design parameters as printed, for the cross-batch comparison.
# `None` means the page does not state it.
DESIGN = {
    "2017-05-12": {
        "charge_time_min_0_80_soc": "~8 to 13.3 (varies by policy)",
        "eol_criterion_as_printed": "80% of nominal capacity (0.88 Ah)",
        "rest_after_80pct_soc": "1 min",
        "rest_after_discharge": "1 s",
        "n_rests": 2,
        "initial_c_over_10_cycle": True,
        "final_c_over_10_cycle": None,
        "cv_cutoff_current": "C/50 (charge and discharge)",
        "ir_pulse_width_ms": 30,
        "replicates_per_policy": "generally 2, except 3.6C(80%)",
    },
    "2017-06-30": {
        "charge_time_min_0_80_soc": "fixed at 10",
        "eol_criterion_as_printed": "75% of nominal capacity (0.88 Ah)  <-- internally inconsistent",
        "rest_after_80pct_soc": "5 min",
        "rest_after_discharge": "5 min",
        "n_rests": 2,
        "initial_c_over_10_cycle": True,
        "final_c_over_10_cycle": None,
        "cv_cutoff_current": "C/50 (charge and discharge)",
        "ir_pulse_width_ms": 30,
        "replicates_per_policy": "generally 1, except 4.8C(80%) (three cells)",
    },
    "2018-04-12": {
        "charge_time_min_0_80_soc": "fixed at 10",
        "eol_criterion_as_printed": "80% of nominal capacity (0.88 Ah)",
        "rest_after_80pct_soc": "5 s",
        "rest_after_discharge": "5 s",
        "n_rests": 4,  # after 80% SOC, after IR test, before discharge, after discharge
        "initial_c_over_10_cycle": None,  # page says only a FINAL C/10 cycle
        "final_c_over_10_cycle": True,
        "cv_cutoff_current": "C/20 (charge and discharge)",
        "ir_pulse_width_ms": 33,
        "replicates_per_policy": "3-8 per policy",
    },
}


def cell_issues(batch_date: str, channel: int) -> list[str]:
    return CELL_ISSUES.get((batch_date, channel), [])
