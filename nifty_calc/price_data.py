"""yfinance batch downloading with local parquet caching and automatic
resolution fallback when fine-grained intraday history isn't available for
the requested historical range.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config
from nifty_calc.ssl_bootstrap import ensure_local_ca_trusted

ensure_local_ca_trusted()

import yfinance as yf  # noqa: E402 - must import after CA bootstrap above


def _cache_path(ticker: str, interval: str) -> Path:
    safe_ticker = ticker.replace("^", "_IDX_")
    return config.PRICE_CACHE_DIR / f"{safe_ticker}__{interval}.parquet"


def _load_meta() -> dict:
    if config.CACHE_META_PATH.exists():
        return json.loads(config.CACHE_META_PATH.read_text())
    return {}


def _save_meta(meta: dict) -> None:
    config.CACHE_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.CACHE_META_PATH.write_text(json.dumps(meta, indent=2, default=str))


def _read_cache(ticker: str, interval: str) -> pd.DataFrame | None:
    path = _cache_path(ticker, interval)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _write_cache(ticker: str, interval: str, df: pd.DataFrame) -> None:
    config.PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_cache_path(ticker, interval))


def _meta_key(ticker: str, interval: str) -> str:
    return f"{ticker}__{interval}"


def _covered_range(meta: dict, ticker: str, interval: str, cached: pd.DataFrame | None):
    """The date range already requested from yfinance for this ticker - not
    just the first/last bar held, which would make a stock listed after the
    requested start (or a range starting on a holiday) look permanently
    incomplete and get re-downloaded on every call. Falls back to the cached
    bars' span for entries written before coverage was tracked."""
    entry = meta.get(_meta_key(ticker, interval), {})
    if "covered_start" in entry and "covered_end" in entry:
        return pd.Timestamp(entry["covered_start"]), pd.Timestamp(entry["covered_end"])
    if cached is not None and not cached.empty:
        return cached.index.min(), cached.index.max()
    return None


def _update_meta_entry(meta: dict, ticker: str, interval: str, df: pd.DataFrame, covered_start, covered_end) -> None:
    meta[_meta_key(ticker, interval)] = {
        "start": str(df.index.min()) if not df.empty else None,
        "end": str(df.index.max()) if not df.empty else None,
        "covered_start": str(covered_start),
        "covered_end": str(covered_end),
        "last_fetched": pd.Timestamp.now("UTC").isoformat(),
    }


def _split_batch_download(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Split a yf.download(group_by='ticker') result into one DataFrame per ticker."""
    if raw is None or raw.empty:
        return {t: pd.DataFrame() for t in tickers}

    result: dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        top_level = set(raw.columns.get_level_values(0))
        for t in tickers:
            result[t] = raw[t].dropna(how="all") if t in top_level else pd.DataFrame()
    else:
        result[tickers[0]] = raw.dropna(how="all")
    return result


def _merge_frames(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return new.sort_index()
    if new is None or new.empty:
        return old.sort_index()
    combined = pd.concat([old, new])
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.sort_index()


def download_batch(
    tickers: list[str], start, end, interval: str, force_refresh: bool = False
) -> dict[str, pd.DataFrame]:
    """Fetch OHLC data for all tickers at one interval, using the local
    parquet cache and only requesting the missing date range from yfinance
    (a single batched yf.download call, never one request per ticker).

    Today's bar is never treated as final: a range reaching today always
    re-requests the last few days so intraday/partial closes get refreshed.

    Returns {ticker: DataFrame} sliced to [start, end].
    """
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    # Bars up to yesterday are final; today's may still change.
    final_through = min(end_ts, pd.Timestamp.today().normalize() - pd.Timedelta(days=1))
    meta = _load_meta()

    cached = {t: (None if force_refresh else _read_cache(t, interval)) for t in tickers}

    # Per ticker, the slice of [start, end] not yet covered.
    windows: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for t in tickers:
        covered = None if force_refresh else _covered_range(meta, t, interval, cached[t])
        if covered is None:
            windows[t] = (start_ts, end_ts)
            continue
        cov_start, cov_end = covered
        need_start, need_end = start_ts < cov_start, end_ts > cov_end
        if need_start and need_end:
            windows[t] = (start_ts, end_ts)
        elif need_start:
            windows[t] = (start_ts, cov_start)
        elif need_end:
            windows[t] = (cov_end - pd.Timedelta(days=5), end_ts)

    if windows:
        to_fetch = list(windows)
        fetch_start = min(w[0] for w in windows.values())
        fetch_end = max(w[1] for w in windows.values())
        raw = yf.download(
            tickers=to_fetch,
            start=fetch_start,
            end=fetch_end + pd.Timedelta(days=1),
            interval=interval,
            group_by="ticker",
            threads=True,
            auto_adjust=False,
            progress=False,
        )
        fetched = _split_batch_download(raw, to_fetch)
        # An entirely empty batch means the request itself failed (network,
        # rate limit) - don't record that range as covered, so it's retried.
        request_ok = any(not df.empty for df in fetched.values())
        for t in to_fetch:
            merged = _merge_frames(cached.get(t), fetched.get(t, pd.DataFrame()))
            cached[t] = merged
            if not merged.empty:
                _write_cache(t, interval, merged)
            if request_ok:
                prev = _covered_range(meta, t, interval, None) if not force_refresh else None
                cov_start = min(fetch_start, prev[0]) if prev else fetch_start
                cov_end = max(final_through, prev[1]) if prev else final_through
                _update_meta_entry(meta, t, interval, merged, cov_start, cov_end)

    _save_meta(meta)

    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = cached.get(t)
        if df is None or df.empty:
            out[t] = pd.DataFrame()
        else:
            out[t] = df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
    return out


def get_prices(
    tickers: list[str], start, end, requested_interval: str = "1d"
) -> tuple[dict[str, pd.DataFrame], str]:
    """Get prices for tickers over [start, end], stepping down through
    config.INTERVAL_FALLBACK_ORDER (starting at requested_interval) until a
    resolution yfinance actually has data for is found.

    Returns (data, interval_actually_used) so the UI can label which
    resolution is being shown.
    """
    order = config.INTERVAL_FALLBACK_ORDER
    start_idx = order.index(requested_interval) if requested_interval in order else len(order) - 1

    for interval in order[start_idx:]:
        data = download_batch(tickers, start, end, interval)
        if any(not df.empty for df in data.values()):
            return data, interval

    return {t: pd.DataFrame() for t in tickers}, order[-1]
