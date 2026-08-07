---
name: forecast-workflow
description: Maps the end-to-end time-series forecasting workflow, naming each phase, its owning skill, its artifact contract, and its checkpoint. Use when orienting to a forecasting project, deciding which phase skill to invoke next, debugging a handoff between phases, or writing orchestration code.
---

# Forecast Workflow — Standard End-to-End

This is the index for the `datascience` skill family. It defines the phase
order, the artifact contract between phases, and which skill owns each phase.
Read it before invoking any individual phase skill so the handoffs line up.

The workflow is a default, not a law. Skip or reorder phases when the project
justifies it, but say so explicitly rather than silently dropping a checkpoint.

## Workflow Phases at a Glance

```
Phase 1: Context contract    → project_context.json          [CHECKPOINT]
Phase 2: EDA                 → eda plots + profiling results [CHECKPOINT]
Phase 3: Preprocessing       → pipeline_spec + splits        [CHECKPOINT]
Phase 4: Feature engineering → updated pipeline_spec         [CHECKPOINT]
Phase 5: Model architecture  → job_specs.json                [CHECKPOINT]
Phase 6: Training execution  → training summary + run store  [monitor, no checkpoint]
Phase 7: Prediction analysis → evaluation report             [CHECKPOINT]
Phase 8: Final synthesis     → research journal index
```

A checkpoint means: stop, present the phase output, and get user confirmation
before starting the next phase.

## Phase Ownership

| Phase | Skill | Primary output |
|---|---|---|
| 1 | orchestrator (no skill) | `outputs/context/project_context.json` |
| 2 | `datascience-ts-eda` (uses `data-profiling`) | `outputs/eda/` |
| 3 | `datascience-preprocessing`, then `datascience-dataset-validator` | `outputs/preprocessing/` |
| 4 | `datascience-feature-engineering` | `outputs/features/` |
| 4b | `datascience-dataset-inspector` | `outputs/dataset_inspection/` |
| 5 | `datascience-model-architect` | `outputs/training/job_specs.json` |
| 6 | `datascience-training-scheduler`, `datascience-training-monitor`, `datascience-model-training` | `outputs/training/`, `outputs/models/` |
| 7 | `datascience-prediction-analysis` | `outputs/evaluation/` |
| 8 | `datascience-research-journal` | `research_journal/` |

---

## Phase 1: Context Contract

**Owner:** the orchestrator, directly. No subagent.

Normalize whatever upstream scoping exists — a project brief, a data
assessment, a ticket, or just the user's answers — into a single
`outputs/context/project_context.json`. Every downstream phase reads this file
and nothing else for problem definition.

Minimum fields:

| Field | Meaning |
|---|---|
| `target` | column being forecast |
| `time_index` | timestamp column |
| `freq` | expected sampling frequency |
| `horizon` | forecast horizon, in steps |
| `dataset_path` | location of the source data |
| `evaluation_metrics` | metrics plus acceptance thresholds |
| `working_hypothesis` | current modeling plan, orchestrator-owned |

If a critical field is missing or is a placeholder, stop and ask the user. Do
not guess a target column or a horizon.

The file is living workflow state, not a frozen decision record. Mark entries
as provisional until the user approves them at a checkpoint.

---

## Phase 2: Exploratory Data Analysis

**Skill:** `datascience-ts-eda`, which uses `data-profiling` for technique
selection and interpretation.

**Input:** `project_context.json`.

**Outputs:**

```
src/eda/                     ← analysis scripts
outputs/eda/plots/           ← PNG evidence
outputs/eda/eda_summary.json ← machine-readable profiling results
```

The orchestrator extracts these profiling results and folds them into the
context contract:

```python
{
    "properties":       {"n_samples": ..., "freq": ..., "missing_ratio": ...},
    "stationarity":     {"is_stationary": bool, "confidence": str},
    "seasonality":      {"seasonal_strength": float, "trend_strength": float, "period": int},
    "memory":           {"hurst": float, "interpretation": str},
    "complexity":       {"permutation_entropy": float, "spectral_entropy": float},
    "autocorrelation":  {"n_significant_lags": int, "first_insignificant_lag": int},
    "missing_gaps":     {"total_missing": int, "gap_count": int, "max_gap_length": int},
}
```

Also record the segment inventory if the EDA found discontinuities, and any
conflict between the data and the context contract.

---

## Phase 3: Preprocessing and Split Validation

**Skills:** `datascience-preprocessing`, then `datascience-dataset-validator`.

**Outputs:**

```
outputs/preprocessing/
  ├── train.csv / val.csv / test.csv
  ├── pipeline_spec.json      ← cleaning, imputation, outliers, resampling
  └── segment_manifest.json   ← only if discontinuities exist
```

`segment_manifest.json` is the single most consequential artifact in the
workflow. If the series has gaps or regime breaks and this file is missing,
every downstream windowed operation will silently bridge the discontinuity.

**The validator gate is mandatory.** `datascience-dataset-validator` returns
`VALID`, `VALID_WITH_RISKS`, or `INVALID`. On `INVALID`, do not proceed to
Phase 4 — return to preprocessing and change the split.

---

## Phase 4: Feature Engineering

**Skill:** `datascience-feature-engineering`.

**Inputs:** `project_context.json`, the preprocessing `pipeline_spec.json`, and
`segment_manifest.json`.

**Output:** `outputs/features/pipeline_spec.json` — the preprocessing spec with
feature steps appended, not a separate file. One spec replays the whole
transformation chain.

| Feature type | Covariate class |
|---|---|
| Calendar (day of week, hour, month) | future |
| Fourier harmonics | future |
| Holiday indicators | future |
| Lag features | past |
| Rolling and expanding statistics | past |
| Entity attributes (store, product, site) | static |

Getting the covariate class wrong is the most common cause of a model that
trains cleanly and cannot predict.

**Phase 4b — dataset inspection.** Run `datascience-dataset-inspector` before
spending training compute. It runs seven programmatic checks and returns a
`PASS`/`WARNING`/`FAIL` verdict. A `FAIL` is blocking.

---

## Phase 5: Model Selection and Architecture

**Skill:** `datascience-model-architect`.

**Inputs:** `project_context.json`, the EDA and preprocessing reports,
`outputs/features/pipeline_spec.json`, and any search-space or budget config
the project ships.

**Output:** `outputs/training/job_specs.json`.

Standard selection hierarchy:

1. A naive baseline — always. Seasonal naive or drift.
2. A statistical baseline — auto-ARIMA or exponential smoothing.
3. Deep learning candidates chosen from EDA signals.
4. A gradient-boosted regressor if the tabular feature set is strong.
5. An ensemble, only if two or more candidates perform well.

| EDA signal | Preferred deep model |
|---|---|
| No usable covariates | N-BEATS |
| Long horizon relative to lookback | TiDE or N-HiTS |
| Rich covariate set, interpretability wanted | Temporal Fusion Transformer |
| Training speed is the constraint | Temporal Convolutional Network |

The architect writes job specs and stops. It does not submit them.

---

## Phase 6: Training Execution

**Skills:** `datascience-training-scheduler` to submit,
`datascience-training-monitor` to poll, `datascience-model-training` for the
modeling detail of what actually runs.

**Outputs:**

```
outputs/training/
  ├── job_specs.json   ← from Phase 5
  └── status.json      ← written at submission, updated on completion
outputs/models/
  ├── <model_name>.<ext>
  └── training_summary.json
```

Every run must be logged to the project's experiment tracker under a single
named experiment. An untracked run cannot be compared, so it did not happen.

The monitor polls on a schedule and reports back. The orchestrator advances to
Phase 7 only after the monitor confirms completion.

---

## Phase 7: Prediction Analysis and Acceptance Review

**Skill:** `datascience-prediction-analysis`.

**Outputs:**

```
outputs/evaluation/
  ├── metrics_summary.json
  ├── residuals_analysis.png
  └── backtest_results.json
```

The phase ends with an explicit verdict against the acceptance criteria in the
context contract: `MET` or `NOT MET`.

On `NOT MET`, diagnose the single largest gap and propose exactly one
iteration. Do not propose five changes at once — you will not know which one
worked.

| Diagnosis | Re-enter phase |
|---|---|
| Data quality, missing covariate | 3 |
| Weak or mis-specified features | 4 |
| Wrong model capacity or search space | 5 |
| Overfitting | 5, with regularization or fewer epochs |
| Distribution shift between splits | 3, split strategy |

---

## Phase 8: Final Synthesis

**Skill:** `datascience-research-journal`.

**Output:** `research_journal/index.md` — executive summary plus links to the
per-phase entries. All runs are logged to the experiment tracker before
synthesis.

---

## Artifact Flow Summary

```
upstream brief / assessment / user answers
        ↓
outputs/context/project_context.json              [Phase 1]
        ↓
outputs/eda/                                      [Phase 2]
        ↓
outputs/preprocessing/pipeline_spec.json
outputs/preprocessing/segment_manifest.json       [Phase 3]
        ↓
outputs/features/pipeline_spec.json               [Phase 4]
outputs/dataset_inspection/inspection_summary.json [Phase 4b]
        ↓
outputs/training/job_specs.json                   [Phase 5]
        ↓
outputs/training/status.json, outputs/models/     [Phase 6]
        ↓
outputs/evaluation/metrics_summary.json           [Phase 7]
        ↓
research_journal/index.md                         [Phase 8]
```

## Adapting the Conventions

The `outputs/` and `src/` layout above is the default. If the project already
has its own convention, follow the project — but keep the artifact *contract*
intact, because each phase skill reads the previous phase's output by role, not
by literal path. Record the actual paths in `project_context.json` so
downstream phases can find them.
