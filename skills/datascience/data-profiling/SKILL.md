---
name: data-profiling
description: Profiles a time series across stationarity, seasonality, long-range memory, entropy, autocorrelation, and missingness, giving the test to run, how to read it, and the preprocessing it implies. Use when writing or reviewing EDA code, interpreting profiling output, or choosing a preprocessing step or model family.
---

# Data Profiling for Time Series

Seven measurements characterize a univariate series well enough to choose
preprocessing steps and a model family. This skill gives the test for each, the
interpretation thresholds, and the action the result implies.

Run all seven. A profiling result you skipped is a modeling decision you made
by accident.

## Toolkit

If the project ships its own profiling module, use it — standardized output is
what downstream phases consume. Otherwise the reference stack is `statsmodels`
for tests and decomposition, `scipy` for distributions, `numpy` for array work,
and optionally `antropy` or `nolds` for entropy and Hurst.

Wrap the results in one dict per series so the shape is stable across projects:

```python
scoring_results = {
    "properties": ...,      # section 7
    "stationarity": ...,    # section 1
    "seasonality": ...,     # section 2
    "memory": ...,          # section 3
    "complexity": ...,      # section 4
    "autocorrelation": ..., # section 5
    "missing_gaps": ...,    # section 6
}
```

## Overview

| What to measure | Test | Decides |
|---|---|---|
| Stationarity | ADF + KPSS | differencing, ARIMA viability |
| Seasonality strength | STL variance ratio | seasonal terms, Fourier features |
| Long-range memory | Hurst exponent | lookback window length |
| Complexity | permutation / sample / spectral entropy | regularization, forecastability |
| Autocorrelation | ACF + PACF | ARIMA orders, minimum lookback |
| Missing gaps | gap-run length distribution | imputation vs. segmentation |
| Series metadata | descriptive statistics | transforms, sanity checks |

## 1. Stationarity

A stationary series has constant mean and variance over time. Classical models
need it; deep models tolerate its absence but still train better without a
strong trend.

Run both tests — they have opposite null hypotheses, and agreement is what
gives you confidence.

```python
from statsmodels.tsa.stattools import adfuller, kpss

adf_stat, adf_p, *_ = adfuller(values, regression="c")
kpss_stat, kpss_p, *_ = kpss(values, regression="c", nlags="auto")

adf_stationary = adf_p < 0.05    # ADF null = has unit root
kpss_stationary = kpss_p > 0.05  # KPSS null = is stationary
```

**Interpretation:**

| ADF | KPSS | Reading | Action |
|---|---|---|---|
| stationary | stationary | confidently stationary | no differencing |
| non-stationary | non-stationary | confidently non-stationary | difference, or model the trend |
| stationary | non-stationary | trend-stationary | detrend or use STL residuals |
| non-stationary | stationary | difference-stationary | first-order differencing |

Use `regression="ct"` instead of `"c"` when the series has a visible
deterministic trend, otherwise ADF will under-reject.

**Preprocessing actions if non-stationary:** first-order differencing, a log
transform to stabilize variance, or STL decomposition keeping the residuals.

## 2. Seasonality Detection

Seasonal strength comes from the variance ratio of an STL decomposition:
`F_s = max(0, 1 - Var(R) / Var(S + R))`, and trend strength is the same formula
with the trend component.

```python
from statsmodels.tsa.seasonal import STL
import numpy as np

res = STL(series, period=period, robust=True).fit()
seasonal_strength = max(0.0, 1 - res.resid.var() / (res.seasonal + res.resid).var())
trend_strength = max(0.0, 1 - res.resid.var() / (res.trend + res.resid).var())
```

**Interpretation:**

- `> 0.6` — strong seasonality. Use a seasonal model or add Fourier features.
- `0.3 – 0.6` — moderate. Seasonal terms are worth including.
- `< 0.3` — weak or absent. Do not force seasonal structure.

**Default period by frequency**, when you have no domain reason to choose:

| Freq | Period | Represents |
|---|---|---|
| hourly | 24 | daily cycle |
| 15-minute | 96 | daily cycle |
| daily | 7 | weekly cycle |
| weekly | 52 | yearly cycle |
| monthly | 12 | yearly cycle |

Multiple seasonalities are common (daily *and* weekly in hourly data). Check
the periodogram for secondary peaks rather than assuming one period.

**Model guidance:** strong seasonality favors models that accept future
covariates, so Fourier terms can be supplied over the horizon. No seasonality
favors N-BEATS or a non-seasonal ARIMA.

## 3. Long-Range Memory (Hurst Exponent)

The Hurst exponent measures persistence. Estimate it with rescaled range (R/S)
or detrended fluctuation analysis; average the two when both are available.
Requires at least ~50 points to be meaningful, and is unreliable below ~200.

```python
import nolds  # optional; otherwise implement R/S directly

h_rs = nolds.hurst_rs(values)
h_dfa = nolds.dfa(values)
```

| `H` | Interpretation | Model implication |
|---|---|---|
| < 0.4 | strongly mean-reverting | mean-reversion features; low-order ARIMA |
| 0.4 – 0.5 | mean-reverting | short memory; short lookback is fine |
| ~0.5 | random walk | hard to forecast; baselines matter most |
| 0.5 – 0.7 | trending | trend features help; deep models benefit |
| > 0.7 | strongly trending | long persistence; extend the lookback window |

An `H` near 0.5 is a warning, not a failure. It means a naive baseline may be
hard to beat, and you should say so before spending training budget.

## 4. Entropy and Complexity

```python
import antropy as ant

permutation_entropy = ant.perm_entropy(values, normalize=True)
sample_entropy = ant.sample_entropy(values)
spectral_entropy = ant.spectral_entropy(values, sf=1.0, normalize=True)
```

| Metric | High means | Low means |
|---|---|---|
| permutation entropy | complex, near-random ordering | regular, predictable ordering |
| sample entropy | irregular, hard to forecast | self-similar, easier to forecast |
| spectral entropy | power spread across frequencies (noise-like) | power concentrated (periodic) |

**Model guidance:** high permutation entropy argues for stronger
regularization — more dropout, a shorter lookback, a smaller model. Low
spectral entropy confirms periodic structure, so Fourier features and seasonal
models will pay off.

## 5. Autocorrelation Structure

```python
from statsmodels.tsa.stattools import acf, pacf

acf_vals, acf_ci = acf(values, nlags=nlags, alpha=0.05)
pacf_vals, pacf_ci = pacf(values, nlags=nlags, alpha=0.05)
```

Set `nlags` to at least two full seasonal periods so you can see the seasonal
spike, and treat a lag as significant when its confidence interval excludes
zero.

Derive:

- `n_significant` — count of significant lags. A high count means long memory,
  so use a longer input window.
- `first_insignificant` — the lag where ACF first stops being significant. Use
  it as a lower bound for the deep-model lookback.
- `decay_rate` — how fast ACF falls off. Slow decay means long memory and often
  means the series needs differencing.
- `pacf_significant_lags` — candidate AR orders.

**Classical order selection:** PACF cutting off at lag *p* with a tailing ACF
suggests AR(*p*). ACF cutting off at lag *q* with a tailing PACF suggests
MA(*q*). Both tailing suggests a mixed ARMA model.

## 6. Missing Value Analysis

What matters is not the total missing count but the *run length* of consecutive
gaps. Ten scattered single points and one ten-step hole need opposite
treatments.

```python
import numpy as np

mask = np.isnan(values)
total_missing = int(mask.sum())
missing_ratio = float(mask.mean())

# Consecutive-gap run lengths.
padded = np.concatenate(([False], mask, [False]))
edges = np.flatnonzero(padded[1:] != padded[:-1])
gap_lengths = (edges[1::2] - edges[0::2]).tolist()
max_gap_length = max(gap_lengths, default=0)
gap_count = len(gap_lengths)
```

**Decision rules:**

| `max_gap_length` | Action |
|---|---|
| 1 – 3 steps | linear interpolation |
| 4 steps to one seasonal period | forward fill or rolling-mean fill |
| longer than one seasonal period | mark a segment boundary; do **not** interpolate across |
| systematic or periodic gaps | investigate the collection process before filling anything |

Standard fill strategies, in rough order of preference: interpolation (linear,
then spline), forward or backward fill, seasonal fill using the prior cycle's
value, rolling-mean fill, constant fill, and dropping rows. Dropping creates an
irregular index and should be a last resort.

Never interpolate across a segment boundary. Bridging a three-day outage
invents data the model will learn as real.

## 7. Series Metadata

Compute descriptive properties alongside the tests — they catch problems the
statistical tests do not.

```python
from scipy import stats

properties = {
    "n_samples": len(values),
    "n_missing": total_missing,
    "missing_ratio": missing_ratio,
    "freq": inferred_freq,
    "start": str(index[0]),
    "end": str(index[-1]),
    "mean": float(np.nanmean(values)),
    "std": float(np.nanstd(values)),
    "min": float(np.nanmin(values)),
    "max": float(np.nanmax(values)),
    "skew": float(stats.skew(values, nan_policy="omit")),
    "kurtosis": float(stats.kurtosis(values, nan_policy="omit")),
    "has_negative": bool(np.nanmin(values) < 0),
    "zero_ratio": float(np.nanmean(values == 0)),
    "n_unique": int(np.unique(values[~mask]).size),
}
```

`has_negative` and `zero_ratio` gate the transform choice: a log transform
needs strictly positive values, and `log1p` needs non-negative ones. A high
`zero_ratio` may mean the series is intermittent, which calls for a different
model family (Croston-style) rather than a different transform.

## Advanced Profiling

Worth adding when the basics leave the modeling choice ambiguous:

| Technique | Purpose |
|---|---|
| changepoint detection | find regime shifts and structural breaks; feeds segmentation |
| cross-correlation with lag | quantify how much lead time a covariate offers |
| micro-backtest | score naive and seasonal-naive baselines to set the floor |
| composite difficulty score | one number combining entropy, memory, and baseline error |

The micro-backtest is the highest-value of these. Knowing the naive baseline's
error before training tells you whether any of the modeling work can pay off.

## Preprocessing Decision Guide

| Profiling finding | Pipeline step |
|---|---|
| non-stationary (unit root) | difference, or take STL residuals |
| strong seasonality | add Fourier or calendar covariates |
| gaps longer than one period | split into segments; write a segment manifest |
| short gaps (1–3 steps) | linear interpolation |
| high variance, positive values | log or Box-Cox transform |
| outliers by IQR or z-score | clip or winsorize |
| skewed distribution | log transform |
| long memory (`H > 0.6`) | larger input window for deep models |
| high permutation entropy | more regularization, shorter lookback |
| high zero ratio | consider an intermittent-demand model |

## Reporting

Emit the profiling results as JSON alongside the human-readable report, so the
orchestrator can fold them into the context contract without re-parsing prose.
Keep the seven top-level keys stable even when a measurement is unavailable —
record `null` with a reason rather than omitting the key.
