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


def _update_meta_entry(meta: dict, ticker: str, interval: str, df: pd.DataFrame) -> None:
    key = f"{ticker}__{interval}"
    meta[key] = {
        "start": str(df.index.min()),
        "end": str(df.index.max()),
        "last_fetched": pd.Timestamp.utcnow().isoformat(),
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

    Returns {ticker: DataFrame} sliced to [start, end].
    """
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    meta = _load_meta()

    cached = {t: (None if force_refresh else _read_cache(t, interval)) for t in tickers}

    to_fetch = [
        t
        for t in tickers
        if cached[t] is None or cached[t].empty
        or cached[t].index.min() > start_ts
        or cached[t].index.max() < end_ts
    ]

    if to_fetch:
        raw = yf.download(
            tickers=to_fetch,
            start=start_ts,
            end=end_ts + pd.Timedelta(days=1),
            interval=interval,
            group_by="ticker",
            threads=True,
            auto_adjust=False,
            progress=False,
        )
        fetched = _split_batch_download(raw, to_fetch)
        for t in to_fetch:
            merged = _merge_frames(cached.get(t), fetched.get(t, pd.DataFrame()))
            cached[t] = merged
            if not merged.empty:
                _write_cache(t, interval, merged)
                _update_meta_entry(meta, t, interval, merged)

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
