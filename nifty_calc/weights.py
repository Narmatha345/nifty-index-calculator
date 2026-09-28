"""Official NIFTY 50 constituent weight history, sourced from NSE Indices
(niftyindices.com) - never invented, never sourced from Yahoo Finance.

NSE Indices publishes "Market Capitalisation, Weightage, Beta for NIFTY 50 &
NIFTY Next 50" monthly (as-of the last trading day of each month), listing
the official weight of all 50 constituents. This module fetches that report,
caches it locally (data/cache/weights/), and normalizes it into a long-format
history table: [as_of_date, ticker, company_name, industry, weight_pct].

If NSE is unreachable for a given month, that month is reported missing
rather than filled with a guess - the caller decides whether to fall back to
a user-supplied verified CSV (see load_reference_weights /
save_reference_weights, used by the Reference Data Manager page).
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd
import requests

import config

HISTORY_COLUMNS = ["as_of_date", "ticker", "company_name", "industry", "weight_pct"]

_MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_LAST_TRADING_DAY_RE = re.compile(r"Last day of trading was\s+(\d{1,2}-[A-Za-z]{3}-\d{4})")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://niftyindices.com/reports/historical-data",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json; charset=utf-8",
}


def _month_year_str(month_start: pd.Timestamp) -> str:
    return f"{_MONTH_ABBR[month_start.month - 1]} {month_start.year}"


def _cache_path(month_start: pd.Timestamp):
    return config.WEIGHTS_CACHE_DIR / f"{month_start:%Y-%m}.csv"


def month_starts_between(start, end) -> list[pd.Timestamp]:
    """Every calendar month-start in [start, end], inclusive of both ends'
    months, clamped to not go earlier than NSE_WEIGHTS_EARLIEST_MONTH."""
    start_ts = max(pd.Timestamp(start).replace(day=1), pd.Timestamp(config.NSE_WEIGHTS_EARLIEST_MONTH))
    end_ts = pd.Timestamp(end).replace(day=1)
    if end_ts < start_ts:
        return []
    return list(pd.date_range(start_ts, end_ts, freq="MS"))


def format_period_label(month_start) -> str:
    return pd.Timestamp(month_start).strftime("%B %Y")


def list_available_periods() -> list[pd.Timestamp]:
    """Month-starts for which an official weight snapshot is already known
    locally (auto-fetched cache and/or the verified reference import) -
    populates the Weight Period selector. Newest first."""
    periods: set[pd.Timestamp] = set()
    if config.WEIGHTS_CACHE_DIR.exists():
        for p in config.WEIGHTS_CACHE_DIR.glob("*.csv"):
            try:
                periods.add(pd.Timestamp(f"{p.stem}-01"))
            except ValueError:
                continue

    reference_df = load_reference_weights()
    if not is_empty(reference_df):
        periods.update(
            pd.Timestamp(period.to_timestamp())
            for period in reference_df["as_of_date"].dt.to_period("M").unique()
        )

    return sorted(periods, reverse=True)


def get_weight_period(month_start, use_network: bool = True) -> pd.DataFrame:
    """The official weight snapshot for exactly ONE calendar month, with no
    fallback to a neighboring month if it's unavailable (unlike get_history,
    which rolls forward to the nearest prior snapshot). This backs the
    explicit Weight Period selector: once a period is chosen, only that
    period's verified data is used for the whole analysis range - never
    silently borrowed from another month. Returns an empty DataFrame if this
    month isn't available from the cache, NSE, or the verified reference
    import - callers must show that as "not available", never estimate it.
    """
    month_start = pd.Timestamp(month_start).replace(day=1)
    df = _read_cache(month_start)
    if df is None and use_network:
        df = fetch_month_from_nse(month_start)
        if df is not None:
            _write_cache(month_start, df)

    if df is None or df.empty:
        reference_df = load_reference_weights()
        if not is_empty(reference_df):
            month_period = month_start.to_period("M")
            match = reference_df[reference_df["as_of_date"].dt.to_period("M") == month_period]
            if not match.empty:
                df = match

    return df if df is not None and not df.empty else pd.DataFrame(columns=HISTORY_COLUMNS)


def parse_mcwb_csv(text: str, month_start: pd.Timestamp) -> pd.DataFrame:
    """Parse one nifty50_mcwb.csv's raw text into the normalized history
    schema. Pure function (no I/O) so it's unit-testable against a fixture.
    """
    raw = pd.read_csv(io.StringIO(text), skiprows=2, dtype=str)
    raw = raw.dropna(how="all")

    sr_no = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
    data_rows = raw.loc[sr_no.notna()]
    if data_rows.empty or data_rows.shape[1] < 7:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    match = _LAST_TRADING_DAY_RE.search(text)
    if match:
        as_of_date = pd.to_datetime(match.group(1), format="%d-%b-%Y")
    else:
        as_of_date = month_start + pd.offsets.MonthEnd(0)

    symbols = data_rows.iloc[:, 1].str.strip()
    names = data_rows.iloc[:, 2].str.strip()
    industries = data_rows.iloc[:, 3].str.strip()
    weights = pd.to_numeric(data_rows.iloc[:, 6], errors="coerce")

    out = pd.DataFrame(
        {
            "as_of_date": as_of_date,
            "ticker": symbols + ".NS",
            "company_name": names,
            "industry": industries,
            "weight_pct": weights,
        }
    )
    return out.dropna(subset=["ticker", "weight_pct"]).reset_index(drop=True)


def fetch_month_from_nse(month_start: pd.Timestamp, timeout: int = 30) -> pd.DataFrame | None:
    """Fetch and parse one month's official weight report directly from NSE
    Indices. Returns None (never a guess) if the month isn't published there
    or the request fails for any reason."""
    try:
        resp = requests.post(
            config.NSE_WEIGHTS_REPORT_ENDPOINT,
            json={
                "SelectedReportType": config.NSE_WEIGHTS_REPORT_TYPE,
                "SelectedDate": "",
                "MonthYear": _month_year_str(month_start),
            },
            headers=_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success") or not payload.get("data"):
            return None
        download_link = payload["data"][0]["DownloadLink"]

        zip_resp = requests.get(
            config.NSE_WEIGHTS_REPORT_BASE_URL + download_link,
            headers={"User-Agent": _HEADERS["User-Agent"]},
            timeout=timeout,
        )
        zip_resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
            csv_name = next(n for n in zf.namelist() if "nifty50_mcwb" in n.lower())
            text = zf.read(csv_name).decode("utf-8", errors="replace")
    except Exception:
        return None

    parsed = parse_mcwb_csv(text, month_start)
    return parsed if not parsed.empty else None


def _read_cache(month_start: pd.Timestamp) -> pd.DataFrame | None:
    path = _cache_path(month_start)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, dtype=str)
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
        df["weight_pct"] = pd.to_numeric(df["weight_pct"])
        return df
    except Exception:
        return None


def _write_cache(month_start: pd.Timestamp, df: pd.DataFrame) -> None:
    config.WEIGHTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_cache_path(month_start), index=False)


def is_empty(df: pd.DataFrame | None) -> bool:
    return df is None or len(df) == 0


def load_reference_weights(path=None) -> pd.DataFrame:
    """Optional, user-supplied fallback: a verified weight-history CSV
    imported via the Reference Data Manager page, used for months NSE
    couldn't be reached for automatically. Empty by default."""
    if path is None:
        path = config.WEIGHTS_REFERENCE_PATH
        if not path.exists():
            return pd.DataFrame(columns=HISTORY_COLUMNS)
    return _parse_normalized_text(_read_source_text(path))


def _read_source_text(source) -> str:
    """Read text from either a filesystem path or a file-like/UploadedFile
    object (e.g. from st.file_uploader), without assuming which."""
    if hasattr(source, "read"):
        source.seek(0)
        data = source.read()
        return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    with open(source, encoding="utf-8", errors="replace") as f:
        return f.read()


def _parse_normalized_text(text: str) -> pd.DataFrame:
    """Parse text already in this app's own weight-history schema
    (as_of_date, ticker, company_name, industry, weight_pct)."""
    df = pd.read_csv(io.StringIO(text), comment="#", dtype=str)
    df = df.dropna(how="all")
    if df.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df["ticker"] = df["ticker"].str.strip()
    df["weight_pct"] = pd.to_numeric(df["weight_pct"], errors="raise")
    for col in ("company_name", "industry"):
        if col not in df.columns:
            df[col] = ""
    return df[HISTORY_COLUMNS].reset_index(drop=True)


def load_uploaded_weights_csv(source) -> pd.DataFrame:
    """Parse a user-uploaded weight CSV for the Reference Data Manager's
    manual-fallback import. Accepts either this app's own normalized schema
    (as_of_date, ticker, ...) or NSE Indices' raw monthly export exactly as
    downloaded from niftyindices.com (nifty50_mcwb.csv, with its
    "Sr. No, Security Symbol, ..., Weightage (%), ..." columns) - whichever
    the file actually is, detected from its content. Never guesses at a
    month for the raw NSE format: it reads the "Last day of trading was ..."
    footer NSE includes in every export, and raises if that's missing.
    """
    text = _read_source_text(source)
    stripped = text.lstrip()

    if stripped.lower().startswith("as_of_date"):
        return _parse_normalized_text(text)

    if "Security Symbol" in text and "Weightage" in text:
        match = _LAST_TRADING_DAY_RE.search(text)
        if not match:
            raise ValueError(
                "This looks like an NSE Indices export, but it's missing the "
                "\"Last day of trading was ...\" line NSE normally includes - "
                "can't determine which month this data is as-of."
            )
        as_of_date = pd.to_datetime(match.group(1), format="%d-%b-%Y")
        return parse_mcwb_csv(text, as_of_date.replace(day=1))

    raise ValueError(
        "Unrecognized CSV format - expected either this app's weight-history schema "
        "(header starting with as_of_date,ticker,...) or NSE Indices' raw monthly "
        "export (nifty50_mcwb.csv, with a Security Symbol / Weightage (%) header)."
    )


def save_reference_weights(df: pd.DataFrame, path=None) -> None:
    path = path or config.WEIGHTS_REFERENCE_PATH
    out = df.copy()
    out["as_of_date"] = pd.to_datetime(out["as_of_date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False, columns=HISTORY_COLUMNS)


def validate_reference_weights(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    for i, row in df.iterrows():
        if not str(row.get("ticker", "")).strip():
            errors.append(f"row {i}: ticker must not be empty")
        w = row.get("weight_pct")
        try:
            w = float(w)
            if not (0 < w <= 100):
                errors.append(f"row {i} ({row.get('ticker')}): weight_pct must be in (0, 100], got {w}")
        except (TypeError, ValueError):
            errors.append(f"row {i} ({row.get('ticker')}): weight_pct is required and must be numeric")
        if pd.isna(row.get("as_of_date")):
            errors.append(f"row {i} ({row.get('ticker')}): as_of_date is required")
    return errors


def get_history(start, end, use_network: bool = True) -> tuple[pd.DataFrame, list[str]]:
    """Official weight history covering every month in [start, end], plus one
    extra month before `start` so callers (see engine.build_weight_panel)
    always have a prior snapshot to hold constant from the very first
    requested date, instead of showing NaN until the range's own first
    monthly snapshot arrives.

    For each month: use the local cache if present, else (if use_network)
    fetch it live from NSE Indices and cache it, else fall back to any
    matching month in the user-supplied reference CSV. A month with no data
    from any of these sources is reported in `missing_months` - never
    silently skipped or fabricated.

    Returns (history_df, missing_months) where missing_months is a list of
    "YYYY-MM" strings.
    """
    lookback_start = pd.Timestamp(start) - pd.DateOffset(months=1)
    months = month_starts_between(lookback_start, end)
    reference_df = load_reference_weights()
    reference_by_month: dict = (
        {period: g for period, g in reference_df.groupby(reference_df["as_of_date"].dt.to_period("M"))}
        if not is_empty(reference_df)
        else {}
    )

    frames: list[pd.DataFrame] = []
    missing_months: list[str] = []

    for month_start in months:
        df = _read_cache(month_start)
        if df is None and use_network:
            df = fetch_month_from_nse(month_start)
            if df is not None:
                _write_cache(month_start, df)

        if df is None or df.empty:
            month_key = pd.Timestamp(month_start).to_period("M")
            ref_df = reference_by_month.get(month_key)
            if ref_df is not None and not ref_df.empty:
                df = ref_df
            else:
                missing_months.append(f"{month_start:%Y-%m}")
                continue

        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=HISTORY_COLUMNS), missing_months

    history = pd.concat(frames, ignore_index=True)
    history = history.drop_duplicates(subset=["as_of_date", "ticker"], keep="last")
    return history.sort_values(["as_of_date", "ticker"]).reset_index(drop=True), missing_months


def get_weight_snapshot(history_df: pd.DataFrame, as_of_date) -> pd.DataFrame:
    """The most recent monthly weight snapshot on/before as_of_date, as a
    DataFrame indexed by ticker with columns [company_name, industry,
    weight_pct, as_of_date]. Empty if as_of_date is before the earliest
    snapshot available - never extrapolated backwards."""
    if is_empty(history_df):
        return pd.DataFrame(columns=["company_name", "industry", "weight_pct", "as_of_date"])

    as_of = pd.Timestamp(as_of_date)
    eligible_dates = history_df.loc[history_df["as_of_date"] <= as_of, "as_of_date"]
    if eligible_dates.empty:
        return pd.DataFrame(columns=["company_name", "industry", "weight_pct", "as_of_date"])

    latest = eligible_dates.max()
    snap = history_df.loc[history_df["as_of_date"] == latest].set_index("ticker")
    return snap[["company_name", "industry", "weight_pct", "as_of_date"]]


def all_tickers(history_df: pd.DataFrame) -> list[str]:
    if is_empty(history_df):
        return []
    return sorted(history_df["ticker"].unique().tolist())
