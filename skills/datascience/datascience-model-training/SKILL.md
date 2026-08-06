---
name: datascience-model-training
description: Train and tune time-series forecasting models — baselines, statistical models, deep architectures, gradient-boosted regressors, and ensembles — with segment-aware series construction, hyperparameter search, backtesting, and experiment tracking. Use for the modeling detail of phase 6 of the forecasting workflow.
---

# Model Training

You train the forecasting models. This skill covers **how** models are fit and
compared; `datascience-model-architect` decides which ones, and
`datascience-training-scheduler` handles submission to a compute backend.

Every run must be logged to the project's experiment tracker under one named
experiment. An untracked run cannot be compared to anything, so for practical
purposes it did not happen.

## Responsibilities

### 1. Baseline First

Fit a naive baseline — seasonal naive, drift, or last-value — before anything
else, and record its error. Every subsequent model is judged against this
number. A deep model reporting 12% SMAPE means nothing until you know the
seasonal naive scores 11%.

### 2. Statistical Models

Auto-ARIMA, exponential smoothing, or Theta. They need no covariates, fit in
seconds, and beat deep models more often than the literature suggests —
particularly on short series and long horizons.

### 3. Deep Learning Models

N-BEATS for univariate problems without covariates. N-HiTS or TiDE for long
horizons. Temporal Fusion Transformer when the covariate set is rich and
attention-based interpretability is wanted. Temporal Convolutional Network when
training throughput matters.

Match capacity to the usable window count from the dataset inspection, not to
the row count.

### 4. Gradient-Boosted Regressors

LightGBM or XGBoost over the lagged feature matrix. Frequently the best
accuracy per unit of compute on tabular-rich forecasting problems. They cannot
extrapolate beyond the training range, so pair them with a trend model or
detrend first when the series trends.

### 5. Hyperparameter Tuning

Use Bayesian optimization — Optuna or equivalent — rather than grid search.
Define search spaces per model family. Optimize against validation performance
using the metric from the context contract, not a default. Log every trial.

Prune unpromising trials early; most of the search budget is otherwise spent
confirming that bad configurations are bad.

### 6. Backtesting and Cross-Validation

Evaluate with rolling-origin backtesting — expanding or sliding window — not a
single holdout. A single holdout gives one sample of the error distribution,
which is not enough to rank models that are close.

Keep the stride and horizon consistent across all models. Two models evaluated
on different origins are not comparable.

### 7. Model Comparison

Compare every model on the same backtest windows. Report MASE, SMAPE, RMSE, and
MAE.

Prefer **MASE** for cross-series comparison: it is scale-free and its baseline
is the naive forecast, so `MASE < 1` means the model beat naive and `MASE > 1`
means it did not. MAPE is unusable when the target approaches zero and
asymmetric otherwise — report it only if the project explicitly asks.

Rank models and select the best, but report the spread across backtest windows
too. A model that wins on average while failing catastrophically on two windows
is often the wrong choice.

### 8. Ensembling

When two or more models perform well, try a simple average and a
validation-weighted average. Compare the ensemble against its best member.
Ensembles usually help, but not always, and the extra serving complexity needs
to earn its place.

### 9. Stuck Detection

Monitor progress. Terminate a job with no metric improvement for N epochs
(default 20) or M minutes (default 30), and mark it `stuck` with the reason. A
hung job silently consumes the budget for the jobs behind it.

## Handling Discontinuous Data

If preprocessing produced a `segment_manifest.json`, this section is not
optional.

- **Do not build a single series spanning the whole timeline.** That forces the
  model to learn across gaps and generates training windows that straddle
  discontinuities.
- **Build one series per contiguous segment.** Each manifest entry becomes its
  own series object.
- **Pass the segments as a list.** Most forecasting libraries accept a sequence
  of series and will construct windows independently within each. Use that.
- **Drop short segments.** A segment shorter than lookback plus horizon yields
  no training window. Exclude it and log the exclusion — silently dropping data
  makes the sample count irreproducible.
- **Keep covariates segment-matched.** When passing a list of target series,
  the covariate lists must be in the same order with matching time indices per
  segment. A misalignment here trains the model on the wrong covariates and
  produces no error.

Every training window the model sees must contain temporally contiguous,
operationally consistent data.

## Toolkit

Use the project's training library and registry when it ships one — the
standardized result format is what the evaluation phase consumes. Otherwise
`darts` or `statsforecast`/`neuralforecast` for the models, `optuna` for
tuning, and `mlflow` or an equivalent tracker for runs.

Whatever the library:

- Set the output length to the contract horizon.
- Pass past, future, and static covariates through their correct channels — the
  classification comes from the feature engineering report.
- Configure accelerators explicitly rather than relying on auto-detection.
- Persist every fitted model, not just the winner. Re-fitting to reproduce a
  result is a waste and often is not bit-identical.
- Set and record the random seed.

## Experiment Tracking

For every run log: the `pipeline_id`, the full hyperparameter set, all backtest
metrics per window, wall-clock duration, resource usage, the library version,
and the random seed.

Use one named experiment for the project. Never disable tracking to "just try
something quickly" — that run is the one you will want to reproduce.

## Output Format

Code in `src/models/`. Models in `outputs/models/`. Logs in
`outputs/models/logs/`.

Produce a training report with:

- **Jobs executed** — total, completed, failed, stuck.
- **Baseline** — the naive baseline error, stated first.
- **Results table** — model, family, MASE, SMAPE, MAE, RMSE, duration, sorted
  by the contract's primary metric.
- **Backtest stability** — metric spread across windows per model, not just the
  mean.
- **Experiment tracker** — experiment name and run identifiers.
- **Best model** — name, configuration, metrics, and margin over the baseline.
- **Hyperparameter tuning** — best parameters per model and the search budget
  spent.
- **Training time** — wall-clock per model.
- **Terminations** — jobs killed for being stuck, with the reason.
- **Recommendations** — which model to carry to prediction analysis and why.

If nothing beat the naive baseline, say so plainly at the top of the report.
That is a legitimate and important result, and burying it wastes the next
iteration.

Return the report to the orchestrator.
