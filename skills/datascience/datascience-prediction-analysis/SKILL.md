---
name: datascience-prediction-analysis
description: Evaluates forecast predictions — metrics against a baseline, residual analysis, interval calibration, error decomposition, and an acceptance verdict — then recommends one highest-impact iteration. Use when a model has finished training, or when deciding whether results are good enough to ship.
---

# Prediction Analysis

You evaluate the trained forecasts and decide whether the project's acceptance
criteria are met. When they are not, you diagnose why and propose **one**
iteration.

One, not five. Changing five things at once means the next round cannot tell
which one helped.

## Context Contract

Read `outputs/context/project_context.json` for the evaluation metrics,
acceptance criteria, business success definition, and backtesting expectations.
Read the training report and the model artifacts. See the `forecast-workflow`
skill for the field list.

Use the project's backtest configuration when it exists. If evaluation settings
are absent from the contract, state the ones you chose and why, so the numbers
are interpretable.

## Responsibilities

### 1. Metrics

Compute on the test set: MASE, SMAPE, RMSE, MAE, and R². Compute MAPE only if
the project asked for it — it is undefined near zero and asymmetric everywhere
else.

**Always report the naive baseline alongside.** A model's absolute error is
uninterpretable without it. MASE does this implicitly, which is why it is the
preferred headline metric: below 1 beats naive, above 1 does not.

Compute at every aggregation level the business actually uses. A model can be
excellent daily and useless weekly, or the reverse, and only one of those
matters to the decision the forecast feeds.

Compare test against validation performance. A large gap is overfitting; test
substantially better than validation usually means the test split is easier,
which is a split problem, not a win.

### 2. Residual Analysis

- Plot residuals over time. Any visible structure means the model missed
  something learnable.
- Check the residual distribution — approximately zero mean, roughly
  symmetric. A non-zero mean is systematic bias and is usually trivially
  fixable.
- Run a Ljung–Box test for residual autocorrelation. Significant
  autocorrelation means exploitable structure remains.
- Check for heteroscedasticity. Residual variance growing with the level
  argues for a log transform.

Residual structure is the highest-signal diagnostic in this phase. Read it
before looking at anything else.

### 3. Prediction Intervals

For probabilistic models:

- Generate and plot intervals at the relevant confidence levels.
- Compute empirical coverage — the fraction of actuals falling inside each
  interval.
- Assess calibration: a 90% interval should contain ~90% of actuals. Systematic
  over-coverage means the intervals are too wide to be useful; under-coverage
  means they understate risk, which is the more dangerous direction.
- Report interval width alongside coverage. An interval spanning the full
  historical range achieves perfect coverage and carries no information.

For point-forecast models, say so explicitly rather than omitting the section.
Downstream decisions often assume intervals exist.

### 4. Backtesting Visualization

- Actual versus predicted over the test period.
- Rolling-origin forecast plots showing prediction from multiple origins.
- Error over time, with high-error regions highlighted.
- Per-horizon error: accuracy at step 1 versus step h. Error grows with
  horizon, and knowing the shape of that growth tells you the usable horizon,
  which is frequently shorter than the requested one.
- Separate plots per segment or regime when the series is long or segmented.

### 5. Error Decomposition

Break error down by condition to find systematic weakness:

- By calendar position — day of week, hour, month.
- By segment or regime.
- By target level — errors at peaks and troughs versus the middle of the
  distribution.
- By horizon step.

Peak error usually matters more than average error, because peaks are usually
why the forecast was commissioned. Report it separately.

### 6. Acceptance Evaluation

State explicitly: `Acceptance criteria: MET` or
`Acceptance criteria: NOT MET`, with the criterion and the observed value side
by side.

Then judge practical adequacy separately from metric adequacy. A model can hit
its SMAPE target and still be unusable — if it misses every peak, or its error
grows past the horizon the decision needs, or its intervals are too wide to act
on. Say so when it happens.

### 7. Iteration Recommendation

Diagnose the single largest gap and propose one change:

| Diagnosis | Action | Re-invoke |
|---|---|---|
| residual seasonality | add seasonal or Fourier features | `datascience-feature-engineering` |
| residual trend | difference, or add trend features | `datascience-preprocessing` |
| high error in specific periods | add calendar or event features | `datascience-feature-engineering` |
| overfitting (validation ≫ test) | regularize, simplify, or get more data | `datascience-model-training` |
| outlier-driven error | revisit outlier treatment | `datascience-preprocessing` |
| distribution shift between splits | revisit the split strategy | `datascience-preprocessing` |
| error grows sharply with horizon | reduce the horizon, or use a direct multi-step model | `datascience-model-architect` |
| uniformly poor, baseline not beaten | different model family, or accept the series is not forecastable | `datascience-model-architect` |

That last row is a real outcome. If the EDA reported a Hurst exponent near 0.5
and high entropy, the honest conclusion may be that this series does not
support a useful forecast. Saying so is more valuable than a tenth iteration.

## Toolkit

Use the project's evaluation module when it ships one — consistent metric
definitions matter more than the specific implementation. Otherwise
`scikit-learn` and `statsmodels` for metrics and tests,
`statsmodels.stats.diagnostic.acorr_ljungbox` for residual autocorrelation,
`scipy.stats` for normality, and `matplotlib` for plots.

Define MASE's in-sample naive denominator once and reuse it. An inconsistent
denominator makes MASE values incomparable across reports, which removes the
only reason to use it.

Log the evaluation to the experiment tracker alongside the training runs, so
metrics and models stay linked.

## Output Format

Code in `src/evaluation/`. Plots and reports in `outputs/evaluation/`. Save
`metrics_summary.json` and `backtest_results.json` for machine consumption.

Produce an evaluation report with:

- **Headline** — best model, its MASE, and whether it beat the naive baseline.
- **Test set metrics** — full comparison table including the baseline row.
- **Validation versus test** — the overfitting check.
- **Acceptance evaluation** — criterion, observed value, `MET` / `NOT MET`, and
  the practical adequacy judgment.
- **Residual summary** — mean, standard deviation, Ljung–Box result, normality,
  heteroscedasticity.
- **Prediction interval coverage** — coverage and width per confidence level,
  or an explicit note that the model is point-only.
- **Per-horizon error** — the error curve and the usable horizon it implies.
- **Error patterns** — systematic weaknesses by condition.
- **Experiment tracker** — run identifiers for the evaluation.
- **Iteration recommendation** — the single highest-impact next step, the skill
  to re-invoke, and the expected effect.

Return the report to the orchestrator.
