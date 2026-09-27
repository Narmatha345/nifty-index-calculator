"""Pure calculation functions for the free-float market-cap index
reconstruction. No I/O, no Streamlit - everything here takes pandas
DataFrames/Series in and returns them out, so it's unit-testable in
isolation from yfinance and the UI.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nifty_calc import divisor as divisor_mod
from nifty_calc import reference_data


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


def compute_ffmc(price: pd.Series, shares: pd.Series, iwf: pd.Series) -> pd.Series:
    """Free-float market cap per stock: Price * Shares * IWF."""
    return price * shares * iwf


def compute_index_value(total_ffmc: float, divisor: float) -> float:
    if divisor is None or divisor <= 0:
        raise ValueError("divisor must be a positive, calibrated value")
    return total_ffmc / divisor


def calibrate_divisor(price: pd.Series, shares: pd.Series, iwf: pd.Series, official_index_value: float) -> float:
    total_ffmc = float(compute_ffmc(price, shares, iwf).sum())
    return divisor_mod.calibrate_divisor(total_ffmc, official_index_value)


def snapshot_at(
    as_of_date,
    constituents_ref: pd.DataFrame,
    divisor_ref: pd.DataFrame,
    close_panel: pd.DataFrame,
    published_weights: pd.Series | None = None,
) -> pd.DataFrame:
    """Per-ticker snapshot as of as_of_date: price, shares, iwf, free-float
    market cap, calculated weight, price change, and point contribution.

    Returns an empty DataFrame if constituent data, divisor, or price data
    is unavailable for this date - callers must surface that as MISSING
    DATA, never compute with placeholders.
    """
    snap = reference_data.get_snapshot(constituents_ref, as_of_date)
    if snap.empty or close_panel.empty:
        return pd.DataFrame()

    div = divisor_mod.get_divisor(divisor_ref, as_of_date)
    if div is None:
        return pd.DataFrame()

    as_of_ts = pd.Timestamp(as_of_date)
    available_dates = close_panel.index[close_panel.index <= as_of_ts]
    if len(available_dates) == 0:
        return pd.DataFrame()
    latest_date = available_dates[-1]
    prior_dates = available_dates[:-1]
    prior_date = prior_dates[-1] if len(prior_dates) > 0 else None

    tickers = [t for t in snap["ticker"] if t in close_panel.columns]
    if not tickers:
        return pd.DataFrame()

    snap_idx = snap.set_index("ticker").reindex(tickers)
    price = close_panel.loc[latest_date, tickers].reindex(tickers)
    if prior_date is not None:
        prior_price = close_panel.loc[prior_date, tickers].reindex(tickers)
    else:
        prior_price = pd.Series(np.nan, index=tickers)

    ffmc = compute_ffmc(price, snap_idx["shares_outstanding"], snap_idx["iwf"])
    total_ffmc = float(ffmc.sum())
    calc_weight_pct = (ffmc / total_ffmc * 100) if total_ffmc else pd.Series(np.nan, index=tickers)
    point_contribution = ffmc / div
    price_change_pct = (price - prior_price) / prior_price * 100

    result = pd.DataFrame(
        {
            "ticker": tickers,
            "price": price.values,
            "shares_outstanding": snap_idx["shares_outstanding"].values,
            "iwf": snap_idx["iwf"].values,
            "free_float_market_cap": ffmc.values,
            "calculated_weight_pct": calc_weight_pct.values,
            "price_change_pct": price_change_pct.values,
            "point_contribution": point_contribution.values,
        }
    )
    if published_weights is not None:
        result["published_weight_pct"] = result["ticker"].map(published_weights)

    result["as_of_date"] = latest_date
    return result.sort_values("free_float_market_cap", ascending=False).reset_index(drop=True)


def reconstruct_series(
    dates,
    close_panel: pd.DataFrame,
    constituents_ref: pd.DataFrame,
    divisor_ref: pd.DataFrame,
    official_series: pd.Series | None = None,
) -> pd.DataFrame:
    """Calculated NIFTY value for each date in `dates`, using the
    constituent shares/IWF/membership and divisor applicable on that date.

    Rows with insufficient reference/price data get calculated=NaN rather
    than a guessed number.
    """
    rows = []
    for d in dates:
        ts = pd.Timestamp(d)
        snap = reference_data.get_snapshot(constituents_ref, ts)
        div = divisor_mod.get_divisor(divisor_ref, ts)
        calculated = np.nan
        if not snap.empty and div is not None and not close_panel.empty and ts in close_panel.index:
            tickers = [t for t in snap["ticker"] if t in close_panel.columns]
            if tickers:
                snap_idx = snap.set_index("ticker").reindex(tickers)
                price = close_panel.loc[ts, tickers].reindex(tickers)
                ffmc = compute_ffmc(price, snap_idx["shares_outstanding"], snap_idx["iwf"])
                calculated = compute_index_value(float(ffmc.sum()), div)
        rows.append({"date": ts, "calculated": calculated})

    result = pd.DataFrame(rows).set_index("date")
    if official_series is not None:
        result["official"] = official_series.reindex(result.index)
    return result.reset_index()


def contribution_analysis(
    start_date,
    end_date,
    close_panel: pd.DataFrame,
    constituents_ref: pd.DataFrame,
    divisor_ref: pd.DataFrame,
) -> pd.DataFrame:
    """Per-ticker point contribution to the calculated index's change over
    [start_date, end_date]. If the divisor changes within the range, the
    range is split into sub-periods at each divisor-change date so
    contributions still reconcile exactly to the total calculated move.
    """
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
    breakpoints = _divisor_change_dates(divisor_ref, start_ts, end_ts)
    period_bounds = sorted({start_ts, end_ts, *breakpoints})

    contributions: dict[str, float] = {}
    for lo, hi in zip(period_bounds[:-1], period_bounds[1:]):
        contributions = _accumulate_period_contribution(
            contributions, lo, hi, close_panel, constituents_ref, divisor_ref
        )

    if not contributions:
        return pd.DataFrame(columns=["ticker", "point_contribution"])

    result = pd.DataFrame(
        {"ticker": list(contributions.keys()), "point_contribution": list(contributions.values())}
    )
    return result.sort_values("point_contribution", ascending=False).reset_index(drop=True)


def _divisor_change_dates(divisor_ref: pd.DataFrame, start_ts, end_ts) -> list[pd.Timestamp]:
    if divisor_mod.is_empty(divisor_ref):
        return []
    return [d for d in divisor_ref["effective_from"] if start_ts < d < end_ts]


def _accumulate_period_contribution(
    contributions: dict[str, float],
    lo: pd.Timestamp,
    hi: pd.Timestamp,
    close_panel: pd.DataFrame,
    constituents_ref: pd.DataFrame,
    divisor_ref: pd.DataFrame,
) -> dict[str, float]:
    div = divisor_mod.get_divisor(divisor_ref, hi)
    snap_lo = reference_data.get_snapshot(constituents_ref, lo)
    snap_hi = reference_data.get_snapshot(constituents_ref, hi)
    if div is None or snap_lo.empty or snap_hi.empty or close_panel.empty:
        return contributions
    if lo not in close_panel.index or hi not in close_panel.index:
        return contributions

    lo_idx = snap_lo.set_index("ticker")
    hi_idx = snap_hi.set_index("ticker")
    common_tickers = sorted(set(lo_idx.index) & set(hi_idx.index) & set(close_panel.columns))

    for t in common_tickers:
        price_lo = close_panel.at[lo, t]
        price_hi = close_panel.at[hi, t]
        if pd.isna(price_lo) or pd.isna(price_hi):
            continue
        ffmc_lo = price_lo * lo_idx.at[t, "shares_outstanding"] * lo_idx.at[t, "iwf"]
        ffmc_hi = price_hi * hi_idx.at[t, "shares_outstanding"] * hi_idx.at[t, "iwf"]
        contributions[t] = contributions.get(t, 0.0) + (ffmc_hi - ffmc_lo) / div

    return contributions


def calibrate_divisor_for_date(
    calib_date,
    constituents_ref: pd.DataFrame,
    close_panel: pd.DataFrame,
    official_series: pd.Series,
) -> dict:
    """Run the one-time divisor calibration workflow for a chosen date: find the
    latest trading day on/before calib_date where both constituent and official
    prices are available, compute total free-float market cap on that day, and
    derive the divisor = total_ffmc / official_index_value.

    Raises ValueError with a user-facing message (not a generic KeyError/IndexError)
    if there isn't enough data to calibrate - callers (the Reference Data Manager
    page) should catch this and show it directly, rather than computing a divisor
    from partial/misaligned data.
    """
    calib_ts = pd.Timestamp(calib_date)

    if close_panel.empty or official_series is None or official_series.empty:
        raise ValueError("No price data available near this date.")

    available = close_panel.index[close_panel.index <= calib_ts]
    official_available = official_series.index[official_series.index <= calib_ts]
    if len(available) == 0 or len(official_available) == 0:
        raise ValueError("No trading data on or before this date.")

    use_date = min(available[-1], official_available[-1])
    snap = reference_data.get_snapshot(constituents_ref, use_date)
    snap_tickers = [t for t in snap["ticker"] if t in close_panel.columns]
    if not snap_tickers:
        raise ValueError("No overlap between constituent list and available price data.")

    snap_idx = snap.set_index("ticker").reindex(snap_tickers)
    price = close_panel.loc[use_date, snap_tickers].reindex(snap_tickers)
    official_value = float(official_series.loc[use_date])
    total_ffmc = float(compute_ffmc(price, snap_idx["shares_outstanding"], snap_idx["iwf"]).sum())
    computed_divisor = divisor_mod.calibrate_divisor(total_ffmc, official_value)

    return {
        "use_date": use_date,
        "total_ffmc": total_ffmc,
        "official_value": official_value,
        "divisor": computed_divisor,
        "tickers_used": len(snap_tickers),
        "tickers_total": len(snap),
    }


def accuracy_metrics(calculated: pd.Series, official: pd.Series) -> dict:
    """Error statistics between the calculated and official index series.
    No forcing/adjustment of `calculated` happens here or anywhere else."""
    aligned = pd.DataFrame({"calculated": calculated, "official": official}).dropna()
    if aligned.empty:
        return {
            "current_error": None,
            "mean_absolute_error": None,
            "rmse": None,
            "max_error": None,
            "n_observations": 0,
        }

    diff = aligned["calculated"] - aligned["official"]
    return {
        "current_error": float(diff.iloc[-1]),
        "mean_absolute_error": float(diff.abs().mean()),
        "rmse": float(np.sqrt((diff**2).mean())),
        "max_error": float(diff.abs().max()),
        "n_observations": int(len(aligned)),
    }
