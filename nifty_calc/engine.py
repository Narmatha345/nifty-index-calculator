"""Pure calculation functions for the NIFTY discrepancy analysis tool. No
I/O, no Streamlit - everything here takes pandas DataFrames/Series in and
returns them out, so it's unit-testable in isolation from yfinance/NSE and
the UI.

Calculation model (see README for the full rationale):
  1. Weighted value = Sum(Price[t] * OfficialWeight[t] / 100) for each date,
     using the most recent official NSE monthly weight snapshot on/before
     that date (never interpolated/guessed between snapshots).
  2. That raw weighted value is calibrated ONCE, at a chosen baseline date,
     against the official ^NSEI value on that date, producing a single
     normalization factor.
  3. Calculated NIFTY = raw weighted value * normalization factor, for every
     date - the factor is never recomputed day-to-day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_close_panel(price_dict: dict[str, pd.DataFrame], price_col: str = "Close") -> pd.DataFrame:
    """Combine {ticker: OHLCV DataFrame} into one DataFrame of close prices,
    columns=tickers, index=datetime."""
    series = {}
    for ticker, df in price_dict.items():
        if df is None or df.empty or price_col not in df.columns:
            continue
        series[ticker] = df[price_col]
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).sort_index()


def build_weight_panel(weights_history: pd.DataFrame, dates) -> pd.DataFrame:
    """Wide [date x ticker] weight-percent matrix aligned to `dates`, holding
    each ticker's most recent official monthly NSE weight constant until the
    next snapshot. Cells before a ticker's first snapshot are NaN (never
    back-filled/guessed)."""
    dates_idx = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in dates}))
    if weights_history is None or weights_history.empty:
        return pd.DataFrame(index=dates_idx)

    wide = weights_history.pivot_table(index="as_of_date", columns="ticker", values="weight_pct", aggfunc="last")
    combined_idx = wide.index.union(dates_idx).sort_values()
    wide = wide.reindex(combined_idx).ffill()
    return wide.reindex(dates_idx)


def build_static_weight_panel(weight_series: pd.Series, dates) -> pd.DataFrame:
    """A [date x ticker] weight panel that holds ONE fixed weight vector
    (e.g. a single user-selected official Weight Period) constant across
    every date, rather than rolling forward across monthly snapshots like
    build_weight_panel does. Feeds straight into compute_raw_weighted_series
    below, unchanged."""
    dates_idx = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in dates}))
    return pd.DataFrame(
        np.tile(weight_series.values, (len(dates_idx), 1)),
        index=dates_idx,
        columns=weight_series.index,
    )


def compute_raw_weighted_series(close_panel: pd.DataFrame, weight_panel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """For each date present in both panels: raw weighted value = Sum(price *
    weight/100) over tickers that have BOTH a price and an official weight
    that day. Also returns `coverage_pct` = the share of official index
    weight actually backed by a price that day, so the caller can warn when
    it drops (missing/delisted constituents, holiday mismatches) instead of
    silently understating the total."""
    common_dates = close_panel.index.intersection(weight_panel.index)
    raw = pd.Series(index=common_dates, dtype=float)
    coverage = pd.Series(index=common_dates, dtype=float)

    for d in common_dates:
        w = weight_panel.loc[d].dropna()
        if w.empty:
            raw.loc[d] = np.nan
            coverage.loc[d] = 0.0
            continue
        p = close_panel.loc[d].reindex(w.index)
        valid = p.notna()
        raw.loc[d] = float((p[valid] * w[valid] / 100.0).sum())
        coverage.loc[d] = float(w[valid].sum())

    return raw, coverage


def calibrate_baseline(raw_series: pd.Series, official_series: pd.Series, baseline_date) -> dict:
    """One-time calibration: find the trading day closest to baseline_date
    (preferring the latest day on/before it; if none exists - e.g. baseline_date
    falls right at the start of the fetched range - the earliest day after it)
    where both the raw weighted value and the official index are available,
    and derive normalization_factor = official / raw.

    Raises ValueError (a user-facing message, not a generic KeyError) if
    there isn't enough data to calibrate at all."""
    baseline_ts = pd.Timestamp(baseline_date)

    raw_available = raw_series.dropna()
    official_available = official_series.dropna()
    both = raw_available.index.intersection(official_available.index)
    if len(both) == 0:
        raise ValueError("No overlapping calculated/official data available to calibrate against.")

    on_or_before = both[both <= baseline_ts]
    on_or_after = both[both >= baseline_ts]
    if len(on_or_before) > 0:
        use_date = on_or_before[-1]
    elif len(on_or_after) > 0:
        use_date = on_or_after[0]
    else:
        raise ValueError(f"No calculated/official data available near {baseline_ts.date()} to calibrate against.")

    raw_value = float(raw_available.loc[use_date])
    official_value = float(official_available.loc[use_date])
    if raw_value == 0:
        raise ValueError(f"Raw weighted value on {use_date.date()} is zero - cannot calibrate.")

    return {
        "baseline_date_requested": baseline_ts,
        "baseline_date_used": use_date,
        "raw_value": raw_value,
        "official_value": official_value,
        "normalization_factor": official_value / raw_value,
    }


def compute_calculated_series(raw_series: pd.Series, normalization_factor: float) -> pd.Series:
    return raw_series * normalization_factor


def discrepancy_metrics(calculated: pd.Series, official: pd.Series) -> dict:
    """Error statistics between Calculated and Actual NIFTY. Neither series
    is adjusted to match the other here or anywhere else - this only
    measures the gap, per the analysis-not-correction purpose of this tool."""
    aligned = pd.DataFrame({"calculated": calculated, "official": official}).dropna()
    if aligned.empty:
        return {
            "current_diff": None,
            "current_diff_pct": None,
            "max_abs_diff": None,
            "max_abs_diff_pct": None,
            "max_abs_diff_date": None,
            "mean_abs_diff": None,
            "mean_abs_diff_pct": None,
            "rmse": None,
            "n_observations": 0,
        }

    diff = aligned["calculated"] - aligned["official"]
    pct = diff / aligned["official"] * 100
    max_idx = diff.abs().idxmax()

    return {
        "current_diff": float(diff.iloc[-1]),
        "current_diff_pct": float(pct.iloc[-1]),
        "max_abs_diff": float(diff.abs().max()),
        "max_abs_diff_pct": float(pct.loc[max_idx]),
        "max_abs_diff_date": max_idx,
        "mean_abs_diff": float(diff.abs().mean()),
        "mean_abs_diff_pct": float(pct.abs().mean()),
        "rmse": float(np.sqrt((diff**2).mean())),
        "n_observations": int(len(aligned)),
    }


def flag_large_deviations(calculated: pd.Series, official: pd.Series, threshold_pct: float) -> pd.DataFrame:
    """Dates where |Calculated - Actual| / Actual exceeds threshold_pct.
    Neither series is labeled "correct" - this only surfaces where they
    diverge most, for further investigation."""
    aligned = pd.DataFrame({"calculated": calculated, "official": official}).dropna()
    if aligned.empty:
        return pd.DataFrame(columns=["date", "calculated", "official", "diff", "diff_pct"])

    aligned["diff"] = aligned["calculated"] - aligned["official"]
    aligned["diff_pct"] = aligned["diff"] / aligned["official"] * 100
    flagged = aligned.loc[aligned["diff_pct"].abs() > threshold_pct].reset_index()
    flagged = flagged.rename(columns={flagged.columns[0]: "date"})
    return flagged.sort_values("diff_pct", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
