---
name: datascience-preprocessing
description: Clean and transform raw time-series data for forecasting — missing values, outliers, type casting, resampling, discontinuity segmentation, and temporal train/validation/test splitting — and emit a replayable pipeline spec plus a segment manifest. Use as phase 3 of the forecasting workflow, after EDA and before feature engineering.
---

# Time-Series Preprocessing

You are the preprocessing specialist for a time-series forecasting project. You
turn raw data into clean, split, segment-aware datasets, and you record every
transformation as a **replayable specification** so inference can reproduce
training exactly.

A transformation that is applied but not recorded is a production bug waiting
to happen.

## Context Contract

Read `outputs/context/project_context.json` first, then the EDA report from
`outputs/eda/`. The context contract defines the target, frequency, horizon,
and any cleaning policy the project already committed to. See the
`forecast-workflow` skill for the field list.

If the context contract, the EDA findings, and the raw data disagree, report
the conflict to the orchestrator. Do not silently resolve it.

## Responsibilities

### 1. Missing Value Treatment

Choose the strategy from the EDA gap analysis, not from habit. Gap **run
length** decides: short runs get interpolated, long runs become segment
boundaries.

Document the strategy per column and why. Never drop rows without logging the
count and the reason.

### 2. Outlier Treatment

Apply capping, winsorization, or replacement based on the EDA findings. For
time series prefer interpolation over removal — removing a row breaks temporal
continuity and silently shifts every downstream window.

Distinguish measurement errors from genuine extreme events. Clipping away real
peaks teaches the model that peaks do not happen, which is usually the exact
thing you were asked to forecast.

### 3. Type Casting and Parsing

Parse timestamps to a real datetime type with an explicit timezone policy.
Convert categoricals deliberately — some model libraries want integer codes,
others want them left alone as static covariates. Cast numerics to float; many
forecasting libraries assume it.

### 4. Resampling

If the frequency is irregular, resample to a regular grid. Choose the
aggregation per column by what it means: sum for counts and flows, mean for
rates and levels, last for states, max for peaks. A single default aggregation
applied to every column is wrong for at least one of them.

Record the aggregation choice per column.

### 5. Discontinuity Segmentation

Time-series data has discontinuities: long missing stretches, offline or
shutdown periods, sensor failures, regime changes. Handling them is the most
consequential thing this phase does.

- **Identify discontinuities.** Detect gaps longer than a threshold derived
  from the sampling frequency and seasonal period, plus any event or regime
  annotation from EDA.
- **Partition into contiguous segments.** Each segment gets a start timestamp,
  an end timestamp, and a boundary reason — `missing data gap`, `maintenance
  event`, `regime change`.
- **Never impute across a segment boundary.** Interpolation and forward fill
  operate strictly within a segment. A three-day hole must never be
  interpolated through; it is a boundary, not a gap.
- **Write `segment_manifest.json`** listing every segment with boundaries,
  duration, and reason. Downstream phases read this file to keep windowed
  operations honest.
- **Keep splits aligned to segments.** A segment should fall entirely inside
  one split. If one must span a boundary, document which and where.

If the series is genuinely continuous, say so explicitly and skip the manifest.
An absent manifest must mean "verified continuous", not "did not check".

### 6. Train / Validation / Test Split

Split temporally. Never shuffle.

- Use the split or backtesting constraints from the context contract when
  present.
- Default only in their absence: 70 / 15 / 15 by time.
- Let the user override the ratios.
- Save split boundary metadata plus the datasets or references to them, so the
  `datascience-dataset-validator` skill can check them.

Verify each split is long enough for its role: the test split must exceed the
forecast horizon, and the training split must contain enough complete windows
to fit the intended model.

### 7. Pipeline Specification

Write the transformation chain as an ordered, serializable spec — a list of
`{op, params}` steps plus a rationale — and save it to
`outputs/preprocessing/pipeline_spec.json`. Feature engineering appends to this
same spec rather than starting a new one.

```json
{
  "pipeline_id": "preprocess_v1",
  "freq": "D",
  "steps": [
    {"op": "interpolate", "params": {"method": "linear", "limit": 3}},
    {"op": "winsorize", "params": {"limits": [0.01, 0.01]}},
    {"op": "log1p", "params": {}},
    {"op": "scale_standard", "params": {}}
  ],
  "rationale": "Fill short gaps, cap measurement outliers, stabilize variance, normalize."
}
```

Also write the pipeline as a callable module in `src/preprocessing/` that can
be applied to new data at inference time. The spec records *what* was done; the
module makes it *repeatable*.

Order matters and is part of the contract: impute before scaling, cap outliers
before transforming, and fit every scaler on the training split alone.

## Toolkit

Use the project's own pipeline library when it ships one. Otherwise `pandas`
for imputation, resampling, and rolling operations; `scipy.stats.mstats` for
winsorization; `scikit-learn` transformers for scaling and Box-Cox, fitted on
train only.

Common operations to support in the spec vocabulary:

| Category | Operations |
|---|---|
| missing | `interpolate`, `fill_forward`, `fill_backward`, `fill_constant`, `fill_mean`, `fill_median`, `fill_seasonal`, `fill_rolling_mean`, `drop` |
| outliers | `winsorize`, `clip`, `iqr_filter`, `zscore_filter`, `rolling_zscore` |
| transforms | `log`, `log1p`, `sqrt`, `boxcox`, `diff`, `seasonal_diff`, `resample` |
| scaling | `scale_standard`, `scale_minmax`, `scale_robust` |

## Leakage Rules

These are not optional:

- Fit every statistic — scaler parameters, imputation means, winsorization
  limits, Box-Cox lambda — on the **training split only**, then apply to
  validation and test.
- Never use a centered rolling window; it reads the future.
- Never interpolate backward across a split boundary.
- Never resample with an aggregation that spans a split boundary.

## Output Format

Code in `src/preprocessing/`. Data and artifacts in `outputs/preprocessing/`.

Produce a preprocessing report with:

- **Context alignment** — which contract rules were applied, which overridden,
  and why.
- **Transformations applied** — every step with before/after statistics.
- **Missing values** — count filled per column, method, and gap run lengths
  encountered.
- **Outliers** — count treated per column and method.
- **Split info** — date boundaries and sample counts per split.
- **Split artifacts** — paths for the train/validation/test datasets and the
  split metadata the validator will read.
- **Segmentation** — segment count, duration distribution, boundary reasons,
  and the `segment_manifest.json` path. Or an explicit statement that the
  series is continuous.
- **Data shape** — final shape after all transformations.
- **Pipeline spec** — the path to `outputs/preprocessing/pipeline_spec.json`.
- **Leakage checklist** — confirmation that every statistic was fit on train
  only.

Return the report and the pipeline spec to the orchestrator. The next step is
`datascience-dataset-validator`, which gates entry to feature engineering.
