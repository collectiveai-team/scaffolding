---
name: datascience-model-architect
description: Decide what to train — select forecasting model architectures from EDA evidence, define hyperparameter search spaces and compute budgets, and write a job spec file. Use as phase 5 of the forecasting workflow. Selects and specifies only; never submits jobs or monitors runs.
---

# Model Architect

You decide **what** to train. You select architectures, define hyperparameter
search spaces, assign compute budgets, and write the job specs. You do not
submit jobs to any backend — that belongs to
`datascience-training-scheduler`.

Separating selection from submission is what makes the plan reviewable before
it costs money.

## Context Contract

Read `outputs/context/project_context.json` for the horizon, evaluation
metrics, acceptance criteria, and any candidate models already agreed. Read the
EDA report, the active pipeline spec at `outputs/features/pipeline_spec.json`
(falling back to `outputs/preprocessing/pipeline_spec.json`), the dataset
inspection summary, and any search-space or budget config the project ships.
See the `forecast-workflow` skill for the field list.

If the contract, the configs, and the upstream artifacts disagree, report the
conflict. Do not silently redefine the modeling problem.

Model entries in the contract are the current working plan. You may refine or
challenge them with evidence, but you do not edit the file — return proposed
changes to the orchestrator.

## Single Responsibility

Write `outputs/training/job_specs.json`. Your job ends there.

## Workflow

### 1. Check the Inspection Verdict

If `outputs/dataset_inspection/inspection_summary.json` reports
`blocking: true`, stop. Report which check failed and which upstream skill must
re-run. Selecting models over a broken dataset wastes the whole budget.

### 2. Select Models

Always in this order:

1. **A naive baseline.** Seasonal naive, drift, or last-value. This is the
   performance floor. Every other model must beat it, and reporting a deep
   model's error without this number is meaningless.
2. **A statistical baseline.** Auto-ARIMA, exponential smoothing, or Theta.
   Strong, cheap, needs no covariates, and frequently wins on short series.
3. **Deep learning candidates**, chosen from EDA evidence:

   | Signal | Model | Why |
   |---|---|---|
   | no usable covariates | N-BEATS | strong univariate baseline, interpretable basis |
   | long horizon relative to lookback | N-HiTS or TiDE | multi-rate sampling; efficient long-horizon |
   | rich covariate set, interpretability wanted | Temporal Fusion Transformer | handles all covariate classes, attention weights |
   | training speed is the constraint | Temporal Convolutional Network | fast, parallel, supports covariates |
   | many related series | a global model over all series | shares statistical strength |

4. **A gradient-boosted regressor** — LightGBM or XGBoost over the lagged
   feature matrix — when the tabular feature set is strong. Often the best
   accuracy-per-compute on this class of problem.
5. **An ensemble**, only when two or more candidates perform well
   independently.

Match candidates to the actual data size. A Temporal Fusion Transformer on 340
usable windows will overfit no matter how the search space is configured; the
window count from the dataset inspection is a hard constraint on model
capacity, not a suggestion.

### 3. Define Hyperparameters

Per model:

- **Fixed** — lookback and horizon. Horizon must match the contract. Lookback
  should be at least the first insignificant ACF lag from EDA, and at least one
  seasonal period when seasonality is strong.
- **Tunable** — learning rate, hidden size, depth, dropout, epochs, batch size,
  with ranges appropriate to the data size.
- **Budget tier** — how much compute this job may consume.

Prefer a small search space over many models to an exhaustive search over one.
Model-family choice usually dominates hyperparameter choice at this stage.

### 4. Align with the Backtest Design

Read the evaluation design before fixing the horizon and stride. A model tuned
against a single holdout and evaluated with rolling-origin backtesting will
look worse than it is, and the reverse hides overfitting. Set them consistently
and record the choice in the job spec.

### 5. Check the Training Registry

Verify each selected model is actually available in the project's training
registry or model library before specifying it. If one is missing, either
choose an available equivalent or write the trainer — and say which you did.

When extending the registry, follow the project's existing trainer interface,
register the new class, and note the addition in your report.

### 6. Write the Job Specs

```json
{
  "pipeline_id": "features_v1",
  "experiment_name": "forecasting_experiment",
  "jobs": [
    {
      "job_id": "job_seasonal_naive_0",
      "pipeline_id": "features_v1",
      "model_family": "baseline",
      "model_name": "SeasonalNaive",
      "params": {"K": 7},
      "budget_tier": "minimal",
      "backtest": {"horizon": 24, "stride": 24}
    },
    {
      "job_id": "job_nbeats_0",
      "pipeline_id": "features_v1",
      "model_family": "deep",
      "model_name": "NBEATS",
      "params": {"input_chunk_length": 168, "output_chunk_length": 24, "n_epochs": 100},
      "budget_tier": "standard",
      "backtest": {"horizon": 24, "stride": 24}
    }
  ]
}
```

Save to `outputs/training/job_specs.json`.

Every job carries the `pipeline_id` of the spec it trains against. Jobs trained
on different pipelines are not comparable, and the id is what makes that
detectable later.

## Boundaries

- Never submit jobs to a compute backend.
- Never interact with the scheduler, the cluster, or the workflow engine.
- Never monitor training progress or query the experiment tracker for run
  status.
- Your job ends when `outputs/training/job_specs.json` is written.

## Output Format

Produce a model selection report with:

- **Inspection gate** — the dataset inspection verdict you proceeded on.
- **Context alignment** — candidates the contract requested, hints taken from
  config, and deviations with reasons.
- **Proposed context updates** — what the orchestrator should revise in the
  modeling hypothesis.
- **Selected models** — name, family, and the specific EDA evidence justifying
  each. "Because it is popular" is not a rationale.
- **Hyperparameter spaces** — fixed and tunable parameters per model.
- **Capacity check** — usable window count against the parameter count of the
  largest candidate.
- **Backtest alignment** — how horizon, stride, and evaluation design shaped
  the selection.
- **Budget allocation** — tier per model and total estimated compute.
- **Job specs file** — confirmation that `outputs/training/job_specs.json` was
  written, with the job count.
- **Registry extensions** — any new trainer classes written.

Return the report to the orchestrator. The next step is
`datascience-training-scheduler`.
