# external_comparison/

Scripts behind `../comparison_external_repos.md`. Read-only with respect to the data:
every one opens the three `.mat` files in `Data/` via `matr.py` (mode `"r"`) and writes
nothing back.

Run from the repo root with the project venv:

```bash
cd "$(git rev-parse --show-toplevel)"      # the repository root
for m in compare_repoB repoB_effects savgol_isolate trunc_scan check_counts final_check; do
    .venv/bin/python -I exploration/external_comparison/$m.py
done
```

| script | what it establishes |
|---|---|
| `compare_repoB.py` | Repo B's 139-cell set, its SOH denominator, the 43/139 EOL count, the 5 duplicate barcodes, censored-cell retention |
| `repoB_effects.py` | the continuation label error (§4.4), the artifact cells, a first look at truncation |
| `savgol_isolate.py` | the smoothing displacement in §4.6, by differencing `savgol(raw)` against `savgol(despiked)` |
| `trunc_scan.py` | the 420-cycle truncation scan in §4.7 |
| `check_counts.py` | that `len(summary['cycle'])` never over-runs the cycle groups |
| `final_check.py` | **re-asserts every headline number in the report**; 27 checks, all passing |
| `inspect_isea.py` | the `TDS` struct contents for Repo A |

`final_check.py` is the one to run first: it is the regression test for the whole report.

## External inputs

`inspect_isea.py` and the ISEA rows of `final_check.py` need Repo A's dataset file, which
is **not** in this repository (18.6 MB). Fetch it to the path the scripts expect:

```bash
mkdir -p /tmp/isea && curl -L -o /tmp/isea/Degradation_Prediction_Dataset_ISEA.mat \
  'https://raw.githubusercontent.com/isea-rwth-aachen/battery-degradation-trajectory-prediction/master/Pre-processing%20Codes/Degradation_Prediction_Dataset_ISEA.mat'
```

then point `ISEA_MAT` at it:

```bash
ISEA_MAT=/tmp/isea/Degradation_Prediction_Dataset_ISEA.mat \
  .venv/bin/python -I exploration/external_comparison/inspect_isea.py
```

Repo B needs no external download — its two notebooks are read for their *code*, and
every number attributed to it was recomputed from `Data/*.mat` here.
