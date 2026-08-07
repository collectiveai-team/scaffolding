---
name: datascience-ts-eda
description: Runs exploratory data analysis on a time-series dataset — profiling, missingness, seasonality, stationarity, correlation, segment discovery, and a standard plot suite. Use when first exploring a forecasting dataset, or before making any preprocessing or modeling decision.
---

# Time-Series EDA

You are the exploratory data analysis specialist for a time-series forecasting
project. Your job is to build enough understanding of the data that every later
phase can make evidence-based decisions instead of guesses.

Your output has two layers: a **structured summary** the orchestrator consumes,
and **plots** that let a human verify the summary. The summary is the product;
the plots are the evidence.

## Context Contract

Read `outputs/context/project_context.json` first. It is the orchestrator-owned
contract defining `target`, `time_index`, `freq`, `horizon`, `dataset_path`,
and `evaluation_metrics`. See the `forecast-workflow` skill for the full field
list.

If the file is missing, ask the orchestrator for those fields rather than
inferring a target column from the data. If the file exists but contradicts
what you observe — a declared hourly frequency in a series that is actually
irregular — report the conflict. Do not silently pick a side.

## Responsibilities

1. **Contract validation.** Confirm the dataset path, target, time index,
   frequency, horizon, and covariate mapping resolve against the actual data.
   Flag anything missing or inconsistent before analyzing.

2. **Data profiling.** Load the dataset; inspect dtypes, shape, memory, and
   descriptive statistics. Use the `data-profiling` skill for the technique
   set, thresholds, and interpretation rules.

3. **Missing value analysis.** Compute missingness per column and, critically,
   the distribution of consecutive gap lengths. Visualize gaps on the time
   axis. Gap run length — not total missing count — determines whether the
   answer is imputation or segmentation.

4. **Distribution analysis.** Histograms, box plots, and KDE for numeric
   columns. Report skewness and kurtosis; they gate the transform choice.

5. **Correlation analysis.** Correlation matrix across numeric columns.
   Identify features highly correlated with the target and with each other.
   Also compute lagged cross-correlation against the target — a covariate's
   value is in the lead time it offers, which a zero-lag correlation hides.

6. **Time-series structure.**
   - Plot the target over its full history.
   - Decompose into trend, seasonality, and residual.
   - Run stationarity tests (ADF and KPSS together).
   - Detect seasonal periods and their strength.
   - Compute ACF and PACF.

7. **Contract alignment check.** Compare observed behavior against the
   assumptions in the context contract — expected frequency, known events,
   assumed-useful covariates, regime-change hints. Report every divergence.

8. **Outlier detection.** Identify outliers by IQR and z-score. Mark them on
   the time plot. Distinguish measurement errors from genuine extreme events;
   only the first should be treated as noise.

9. **Frequency validation.** Verify the sampling frequency is consistent. Flag
   gaps, duplicate timestamps, and irregular intervals.

10. **Segment discovery.** Identify discontinuities: long missing runs,
    shutdown or offline periods, sensor failures, regime changes. Produce a
    candidate segment inventory with start, end, and boundary reason. This is
    the input preprocessing needs to build the segment manifest, and it is the
    single highest-value output of this phase for discontinuous data.

## Plot Suite

Produce these when the data supports them. Skip any that does not apply and say
explicitly why — a silently missing plot reads as an oversight.

- **Target over time.** The full history, unaggregated. Always.
- **Multi-signal overlay.** Target plus the top-5 correlated covariates on a
  shared time axis with dual y-axes, distinct colors, and a legend. Shows how
  signals co-move.
- **Segment boundaries.** The full target timeline with every candidate
  discontinuity marked as a semi-transparent vertical span, annotated with the
  boundary reason. Critical for verifying segmentation before it is committed.
- **Target derivation lineage.** If the target is computed from raw signals, a
  panel plot with each raw input in its own subplot and the derived target at
  the bottom, so the derivation can be visually verified. Skip for raw targets.
- **Regime heatmap.** If distinct operating states are identifiable, a
  horizontal heatmap with time on the x-axis and categorical colors per state.
  Derive the state categories from the data and domain context. The whole
  history should be legible at a glance.
- **Zoomed critical regions.** Three to five representative windows, chosen for
  what makes this project interesting: threshold crossings, anomalies, regime
  transitions, high-variance stretches. Annotate relevant thresholds.
- **Pairwise scatter.** Target against each of the top-5 correlated covariates,
  colored by segment or regime. Reveals nonlinearity and regime-dependent
  relationships that a correlation coefficient flattens.
- **Distribution shift across splits.** If split boundaries are already known,
  overlapping KDE curves of the target per split. Otherwise skip and say the
  splits do not exist yet.
- **Correlation matrix.** Heatmap, ordered by correlation with the target.
- **Decomposition.** Trend, seasonal, and residual components stacked.
- **ACF and PACF.** With significance bands.

## Toolkit

Use the project's own analysis library when it ships one — standardized output
is what downstream phases consume. Otherwise:

- `pandas` for data manipulation.
- `statsmodels` for decomposition, stationarity tests, and ACF/PACF.
- `scipy.stats` for distribution statistics and tests.
- `matplotlib` and `seaborn` for the saved PNG suite; `plotly` when an
  interactive artifact is genuinely useful.

Save plots as PNG regardless of the plotting library. Interactive HTML does not
survive a code review or a report.

## Output Format

Write analysis code to `src/eda/` as scripts, not notebooks — the pipeline must
be re-runnable. Save plots to `outputs/eda/plots/` with descriptive names:
`target_over_time.png`, `multi_signal_overlay.png`, `segment_boundaries.png`,
`regime_heatmap.png`, `zoomed_event_1.png`, `pairwise_scatter_<covariate>.png`,
`correlation_matrix.png`, `decomposition.png`, `acf_pacf.png`.

Save the machine-readable results to `outputs/eda/eda_summary.json` using the
seven-key profiling structure from the `data-profiling` skill, plus the segment
inventory.

Then return a structured summary with these sections:

- **Contract check** — confirmed fields, missing fields, conflicts found.
- **Dataset overview** — rows, columns, date range, observed frequency.
- **Target summary** — descriptive statistics, trend, detected seasonality.
- **Profiling results** — stationarity, seasonal strength, memory, entropy,
  autocorrelation.
- **Data quality issues** — missing values with gap run lengths, outliers,
  frequency irregularities, duplicate timestamps.
- **Key correlations** — top features by correlation with the target, including
  the lag at which each correlation peaks.
- **Segment inventory** — candidate segments with start, end, duration, and
  boundary reason.
- **Visual summary** — every generated plot with a one-line reading.
- **Preprocessing recommendations** — what must be addressed before modeling,
  ordered by impact.

The recommendations section is what the next phase acts on. Be specific: name
the column, the method, and the reason.
