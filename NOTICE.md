# NOTICE

## Scope of the MIT licence, and the terms that apply to everything else

[`LICENSE`](LICENSE) is the unmodified MIT licence. It covers **only the code and
prose written for this repository**: the Python modules under `exploration/` and
`exploration/external_comparison/`, and the Markdown documents (`README.md`, this
`NOTICE.md`, `exploration/REPORT.md`, `schema.md`, `step2_findings.md`,
`cleaning_plan.md`, `MANIFEST.md`, `comparison_external_repos.md`, the `figures/`
and `tables/` indexes).

**The dataset carries its own terms.** The three raw `.mat` batch files are distributed
by Toyota Research Institute under **Creative Commons Attribution 4.0 International
(CC BY 4.0)** — <https://creativecommons.org/licenses/by/4.0/> — as stated on TRI's
catalog page at <https://data.matr.io/> for the dataset *"Data-driven prediction of
battery cycle life before capacity degradation"* (23 January 2019). Those files are not
redistributed here.

**The derived data files carry the dataset's terms, not this licence.** Because they are
adaptations of CC BY 4.0 data, `exploration/analysis_set_cells.csv`,
`exploration/analysis_set_cycles.csv`, `exploration/cell_inventory.csv` and
`exploration/tables/*.csv` are made available under **CC BY 4.0**, with the attribution
and statement of modifications given in `README.md` under "Licensing". The figures in
`exploration/figures/` are renderings of that data and are offered on the same terms.

**Upstream's loading code carries no licence.** The MATLAB scripts and
`BuildPkl_Batch*.ipynb` notebooks at
<https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation>
have no licence file, so no rights to copy, modify or redistribute them are granted, and
none of that code is copied, vendored or imported into this repository. The modelling
code for the original paper is separately under an academic licence (obtainable from the
authors) and is not present here and not required by anything here.

---

Questions of fact in this file — which licence applies to which file, and what
each one permits — are set out with their sources in `README.md` under
"Licensing", and the attribution text for the derived data files is given there
verbatim.
