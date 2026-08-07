---
name: datascience-feature-engineering
description: Generates time-series features — lags, rolling statistics, calendar terms, Fourier harmonics — with segment-aware windowing and past/future/static covariate classification. Use when building features for a forecasting model, or when windowed features may be crossing data discontinuities.
---

# Time-Series Feature Engineering

You create the features a forecasting model learns from, classify them by when
they are knowable, and append them to the replayable pipeline spec.

Two mistakes dominate this phase and both are silent: computing a window across
a discontinuity, and classifying a past-only feature as a future covariate.
Either produces a model that trains beautifully and cannot predict. Guard
against both explicitly.

## Context Contract

Read `outputs/context/project_context.json` for feature priorities, event
context, and covariate mapping. Read the EDA report for the seasonal periods
and correlation structure, the preprocessing pipeline spec, and
`segment_manifest.json`. See the `forecast-workflow` skill for the field list.

The contract is living workflow state, not a frozen decision record. Treat
feature entries as the current working hypothesis unless the orchestrator marks
them approved. If the contract conflicts with upstream artifacts, report the
conflict rather than choosing an interpretation.

Do not edit the context file yourself. Return proposed changes to the
orchestrator.

## Responsibilities

### 1. Lag Features

Lag the target and the relevant covariates. Choose lags from the EDA
autocorrelation results rather than by convention:

- Short lags 1 through the first insignificant ACF lag.
- Seasonal lags at each detected period and its multiples.
- The PACF-significant lags, which are the ones a linear model would use.

A lag shorter than the forecast horizon is unusable at prediction time for the
target itself. Check this before creating it.

### 2. Rolling and Expanding Statistics

Rolling mean, standard deviation, min, max, and quantiles over several window
sizes; expanding statistics where a cumulative view is meaningful; exponentially
weighted statistics for recency-biased signals.

Every window must be **trailing**. A centered window reads the future and will
inflate validation scores while destroying production performance.

### 3. Segment-Aware Windowing

If `segment_manifest.json` exists, every windowed computation — lags, rolling,
expanding, EWM — must respect segment boundaries.

- **Lags.** A lag at the first timestep of a segment is `NaN`. It must not
  carry the last value of the previous segment.
- **Rolling.** A window at the start of a segment uses only that segment's
  data. Where insufficient data exists, produce `NaN` or a partial-window
  result — never a value contaminated by the prior segment.
- **EWM and expanding.** Reset state at each boundary.
- **Implementation.** Group by segment ID before any windowed operation, or use
  window functions that take a grouping key.

Without this, the model learns artificial patterns at every boundary that do
not exist in reality. The `datascience-dataset-inspector` skill checks for
exactly this and will fail the dataset if it finds it.

### 4. Calendar Features

Day of week, day of month, month, quarter, year; is-weekend and month/quarter
start and end; week of year and day of year for yearly seasonality; holiday
indicators for the relevant region and calendar.

Encode cyclic features cyclically. Hour 23 and hour 0 are adjacent, which an
integer encoding hides — use sine/cosine pairs or let the model treat it as
categorical.

### 5. Fourier Terms

Sine and cosine pairs for each detected seasonal period, typically three to
five harmonics each. Fourier terms are the standard way to give a model
multiple simultaneous seasonalities without one lag column per period.

Harmonic count is a capacity dial: more harmonics fit sharper seasonal shapes
and overfit faster. Start at three.

### 6. Interaction Features

Cross calendar and numeric variables where domain knowledge suggests a real
interaction. Ratios between related numeric columns. Do not generate the full
pairwise product space — it buries signal in noise and inflates training cost.

### 7. Target Encoding (optional)

Encode high-cardinality categoricals with target statistics. Compute the
encoding inside a cross-validation fold, on training data only. Naive target
encoding is one of the most effective ways to leak the label.

### 8. Feature Selection

- Compute importance with a fast model — gradient-boosted trees or a random
  forest — fit on the training split.
- Drop near-zero-variance features.
- Drop one of each highly collinear pair.
- Report each new feature's correlation with the target, including the lag at
  which it peaks.

Report the ranking. Do not prune aggressively here; the model architect needs
to see what exists.

## Covariate Classification

Classify every feature. This is the contract the training phase depends on.

| Class | Definition | Examples |
|---|---|---|
| **past** | known only up to the present | lagged target, rolling statistics, sensor readings |
| **future** | known over the forecast horizon | calendar terms, Fourier harmonics, holidays, scheduled events, published forecasts |
| **static** | constant over time per entity | store ID, product category, site, capacity |

The test is simple: at prediction time, standing at the forecast origin, do you
have this value for every step of the horizon? If not, it is a past covariate,
whatever it looks like.

Weather is the classic trap. Observed weather is a past covariate; a weather
*forecast* is a future covariate, and the two have different error
characteristics. Do not train on observations and serve on forecasts without
saying so.

## Toolkit

Use the project's own feature library when it ships one. Otherwise `pandas` for
lags, rolling, and calendar extraction; `numpy` for Fourier terms; the
`holidays` package for holiday calendars; `scikit-learn` or `lightgbm` for
importance ranking.

## Extending the Pipeline Spec

Append feature steps to the preprocessing spec rather than starting a new file,
so one spec replays the entire transformation chain:

```json
{
  "pipeline_id": "features_v1",
  "freq": "D",
  "steps": [
    {"op": "interpolate", "params": {"method": "linear", "limit": 3}},
    {"op": "scale_standard", "params": {}},
    {"op": "covariates", "params": {"type": "calendar", "features": ["day_of_week", "month"]}},
    {"op": "covariates", "params": {"type": "fourier", "period": 7, "harmonics": 3}},
    {"op": "covariates", "params": {"type": "lags", "lags": [1, 7, 14], "segment_aware": true}}
  ],
  "rationale": "Preprocessing chain plus calendar, weekly Fourier, and segment-aware lags."
}
```

Save to `outputs/features/pipeline_spec.json`.

## Output Format

Code in `src/features/`. Datasets in `outputs/features/`.

Produce a feature engineering report with:

- **Context alignment** — features requested by the contract, features
  implemented, and justified deviations.
- **Proposed context updates** — what the orchestrator should revise in the
  current feature hypothesis.
- **Features created** — name, description, and covariate class for each.
- **Segment awareness** — confirmation that every windowed feature was computed
  within segments, or an explicit statement that the series is continuous.
- **Feature importance** — top 20 ranked, with the method used.
- **Dropped features** — what was removed and why.
- **Covariate summary** — counts of past, future, and static covariates.
- **Dataset shape** — final shape.
- **Extended pipeline spec** — path to `outputs/features/pipeline_spec.json`.

Return the report and the spec. The next step is
`datascience-dataset-inspector`, which validates the result before training
compute is spent.
