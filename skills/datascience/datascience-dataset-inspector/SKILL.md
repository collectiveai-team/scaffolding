---
name: datascience-dataset-inspector
description: Validate a training dataset before model training with seven programmatic checks — feature completeness, distribution shift, segment-boundary leakage, target representativeness, window completeness, feature range, correlation stability — each returning PASS/WARNING/FAIL with supporting plots. Use after feature engineering and before spending any training compute.
---

# Dataset Inspector

You bridge feature engineering and model training. Your job is to
**programmatically validate** that the training dataset is correct, complete,
and ready for modeling, then produce **visualizations as supporting evidence**.
You catch pipeline bugs, leakage, and distribution problems before they waste
training compute.

Your output has two layers:

1. **Automated checks** — tests producing `PASS` / `WARNING` / `FAIL` verdicts
   with the numbers behind them.
2. **Visualizations** — plots that let a human verify each verdict.

The checks are the product. The plots are the evidence. A plot without a
verdict is decoration.

## Inputs

- The feature datasets in `outputs/features/`.
- The feature importance ranking from the feature engineering report — several
  checks weight their verdict by importance, so a missing ranking degrades the
  inspection.
- `segment_manifest.json` from preprocessing, if the series is discontinuous.
- The intended lookback and horizon, from the pipeline spec or the
  orchestrator.

## Part 1: Automated Validation Checks

Run every check. Each returns a structured verdict with its supporting metrics.

### Check 1: Feature Completeness

For every feature, compute the NaN ratio per split.

- `FAIL` if any top-20 importance feature exceeds 50% NaN in any split.
- `WARNING` if any top-20 feature exceeds 20% NaN, or any feature exceeds 50%.
- `PASS` otherwise.

Report which split has the worst coverage for each flagged feature. A
high-importance feature with high missingness is a worse problem than a
low-importance one with the same ratio.

### Check 2: Distribution Shift Between Splits

For the top-30 features by importance, plus the target:

- Kolmogorov–Smirnov two-sample test between train and test, and between train
  and validation. Flag `p < 0.01`.
- Population Stability Index between train and test.

Verdict:

- `FAIL` if the target, or more than 30% of top-20 features, shows `PSI > 0.25`.
- `WARNING` if the target or any top-20 feature shows `KS p < 0.01` or
  `PSI > 0.1`.
- `PASS` otherwise.

Some shift is expected in a temporal split and is not automatically a bug. Shift
in the *target* is the one that invalidates evaluation.

### Check 3: Leakage Detection at Segment Boundaries

Only applies when segment boundaries exist.

For every boundary, examine the lagged and rolling features on both sides:

- Does `lag_target_1` at the first timestep of a new segment equal the last
  target value of the previous segment? If so, the lag leaked across the
  boundary.
- Does a rolling window at the start of a new segment include prior-segment
  values? Test by recomputing the statistic from the new segment alone and
  comparing.

Report the fraction of boundaries showing leakage.

Verdict:

- `FAIL` if any boundary leaks. Any leakage is a pipeline bug, not a tolerance.
- `PASS` if no leakage, or if there are no boundaries.

### Check 4: Target Representativeness Across Splits

- Compute target statistics per split: mean, std, min, max, P10, P50, P90, P99.
- If a decision threshold is defined, compute the fraction of samples beyond it
  per split. Flag any split with zero events, or a ratio differing by more than
  3× across splits.
- With no threshold, compare P90 and P99 across splits — do extreme values
  appear everywhere?
- Test target stationarity within each split. Differing stationarity between
  train and test is a finding.

Verdict:

- `FAIL` if any split has zero extreme events while others have many. The model
  cannot learn it or be evaluated on it.
- `WARNING` if target statistics differ substantially between splits, or
  stationarity differs.
- `PASS` otherwise.

### Check 5: Window Completeness

Given the lookback and horizon:

- Count the **complete contiguous windows** formable in each split without
  crossing a segment boundary or containing a `NaN` target.
- Report usable windows against the theoretical maximum.
- Check covariate alignment: do past covariates cover every input window, and
  do future covariates extend across input *plus* horizon for every window?

Verdict:

- `FAIL` if under 50% of theoretical windows are usable in any split, or if the
  training split yields fewer than 100 usable windows.
- `WARNING` if under 80% are usable, or if covariate coverage is incomplete for
  more than 10% of windows.
- `PASS` otherwise.

This check is what turns "we have 50,000 rows" into "we have 340 trainable
examples", which is frequently the real story.

### Check 6: Feature Range Validation

For each numeric feature, compute the training min/max, then the fraction of
validation and test values falling outside that range.

Verdict:

- `FAIL` if over 5% of test values are out of training range for any top-10
  importance feature.
- `WARNING` if over 5% for any top-30 feature, or over 1% for any top-10.
- `PASS` otherwise.

Tree models cannot extrapolate at all beyond the training range, so this check
is stricter in effect for gradient-boosted models than for neural ones.

### Check 7: Correlation Sanity

Compute each feature's correlation with the target per split.

- Flag features whose correlation sign flips between train and test.
- Flag features where `|corr_train - corr_test| > 0.3`.

Verdict:

- `WARNING` if any top-20 feature flips sign or shifts by more than 0.3.
- `PASS` otherwise.

A relationship that holds in training and vanishes in test will not generalize,
whatever the validation score says.

## Part 2: Visualizations

### V1. Training Sample Visualization

At least ten samples spanning different regions. Each is a multi-panel plot:

- **Panel 1** — the target over the full window, input plus horizon, with the
  split point marked.
- **Panel 2** — the top-5 past covariates over the input chunk.
- **Panel 3** — the top-5 future covariates over the full window, demonstrating
  they actually extend into the horizon.
- **Panel 4** — segment or regime markers and event annotations, if any.

Annotate each with the timestamp range, segment ID, NaN count in the window,
and target range.

Cover: two early in training, two late in training, two from validation, two
from test, two near notable events or high-variance windows.

Save as `plots/training_sample_{i}.png`.

### V2. Feature Coverage Heatmap

Supports Check 1. Features on the x-axis sorted by missing ratio, time on the
y-axis, color for present versus missing, with split boundaries marked.

Save as `plots/feature_coverage_heatmap.png`.

### V3. Feature Distribution Comparison

Supports Check 2. Overlapping KDE curves per split for the top-20 features, as
a grid of small multiples, each annotated with its KS p-value and PSI.

Save as `plots/feature_distribution_comparison.png`.

### V4. Segment Boundary Leakage Evidence

Supports Check 3. For three to five boundaries, plot the target and top-3
lagged features across the boundary, showing whether values carry over or
correctly reset. Annotate with the leakage result.

Save as `plots/segment_boundary_check_{i}.png`.

### V5. Target Distribution Deep Dive

Supports Check 4. Target distribution on a log y-axis, a Q-Q plot, and a CDF.
Mark the decision threshold on the CDF with per-split event fractions, or P90
and P99 if no threshold exists.

Save as `plots/target_distribution_deep_dive.png`, `plots/target_qq.png`,
`plots/target_cdf.png`.

### V6. Window Alignment Diagram

Supports Check 5. Lookback and horizon mapped onto real data with covariate
alignment, annotated with usable window counts.

Save as `plots/window_alignment_diagram.png`.

## Toolkit

`pandas` for data manipulation, `scipy.stats.ks_2samp` for distribution shift,
`scipy.stats.pearsonr` or `pandas.corr` for correlation,
`statsmodels.tsa.stattools.adfuller` for stationarity, and `matplotlib` with
`seaborn` for plots.

## Output Format

Code in `src/dataset_inspection/`. Plots in
`outputs/dataset_inspection/plots/`.

Save a structured summary to
`outputs/dataset_inspection/inspection_summary.json`:

```json
{
  "overall_status": "PASS | WARNING | FAIL",
  "blocking": false,
  "checks": {
    "feature_completeness": {
      "verdict": "PASS",
      "details": "...",
      "flagged_features": [
        {"name": "...", "nan_pct_train": 0.0, "nan_pct_test": 0.0, "importance_rank": 1}
      ]
    },
    "distribution_shift": {
      "verdict": "WARNING",
      "details": "...",
      "flagged_features": [{"name": "...", "ks_pvalue": 0.004, "psi": 0.14}]
    },
    "leakage_detection": {
      "verdict": "PASS",
      "details": "...",
      "boundaries_checked": 0,
      "boundaries_with_leakage": 0
    },
    "target_representativeness": {
      "verdict": "PASS",
      "details": "...",
      "target_stats_by_split": {}
    },
    "window_completeness": {
      "verdict": "PASS",
      "details": "...",
      "usable_windows": {"train": 0, "val": 0, "test": 0},
      "theoretical_max": {"train": 0, "val": 0, "test": 0}
    },
    "feature_range": {
      "verdict": "PASS",
      "details": "...",
      "out_of_range_features": []
    },
    "correlation_sanity": {
      "verdict": "PASS",
      "details": "...",
      "unstable_features": []
    }
  },
  "total_samples": {"train": 0, "val": 0, "test": 0},
  "feature_count": {"target": 1, "past_covariates": 0, "future_covariates": 0, "static_covariates": 0},
  "plot_files": []
}
```

`overall_status` is the worst verdict across all checks. `blocking` is true if
any check is `FAIL`.

Then produce a markdown report with:

- **Check results summary** — a table of all seven checks with verdict,
  one-line explanation, and the key metric.
- **Blocking issues** — every `FAIL`, with cause and remediation.
- **Warnings** — every `WARNING`, with its consequence for interpretation.
- **Sample visualizations** — the generated plots.
- **Recommendations** — specific fixes naming which upstream skill to
  re-invoke: `datascience-preprocessing` or
  `datascience-feature-engineering`.

Return the report to the orchestrator. If `blocking` is true, state plainly
which checks failed and what must change before training can start.
