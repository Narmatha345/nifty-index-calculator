"""Time-varying constituent reference data: shares outstanding, IWF, and NIFTY
membership windows, each with effective dates.

This module never invents values. If data/reference/constituents.csv has no
data rows (just the annotated template header), every lookup here correctly
reports "no constituents available" rather than falling back to guessed data.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

import config
from nifty_calc.schemas import CONSTITUENT_COLUMNS, ConstituentRow

_FAR_FUTURE = pd.Timestamp.max.normalize()


def load_constituents(path=None) -> pd.DataFrame:
    """Load the constituent reference CSV.

    Comment lines (starting with '#') are the human-readable field guide and
    are skipped. Returns an empty (but correctly typed/columned) DataFrame
    when only the template header is present - this is the expected v1
    starting state, not an error.
    """
    path = path or config.CONSTITUENTS_PATH
    df = pd.read_csv(path, comment="#", dtype=str)
    df = df.dropna(how="all")
    if df.empty:
        return pd.DataFrame(columns=CONSTITUENT_COLUMNS)

    df["ticker"] = df["ticker"].str.strip()
    df["shares_outstanding"] = pd.to_numeric(df["shares_outstanding"], errors="raise")
    df["iwf"] = pd.to_numeric(df["iwf"], errors="raise")
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    df["effective_to"] = pd.to_datetime(df["effective_to"])
    df["member_from"] = pd.to_datetime(df["member_from"])
    df["member_to"] = pd.to_datetime(df["member_to"])
    return df.reset_index(drop=True)


def validate_constituents(df: pd.DataFrame) -> list[str]:
    """Validate each row via ConstituentRow. Returns a list of error strings
    (empty list means the data is structurally valid - it says nothing about
    whether the values are *correct*, only well-formed)."""
    errors: list[str] = []
    for i, row in df.iterrows():
        try:
            ConstituentRow(
                ticker=row["ticker"],
                shares_outstanding=float(row["shares_outstanding"]),
                iwf=float(row["iwf"]),
                effective_from=_to_date(row["effective_from"]),
                effective_to=_to_date(row["effective_to"]),
                member_from=_to_date(row["member_from"]),
                member_to=_to_date(row["member_to"]),
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"row {i} ({row.get('ticker', '?')}): {exc}")
    return errors


def _to_date(value) -> _dt.date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return None
    return pd.Timestamp(value).date()


def is_empty(df: pd.DataFrame) -> bool:
    return df is None or len(df) == 0


def all_tickers(df: pd.DataFrame) -> list[str]:
    """Every ticker that has ever appeared in the reference data, regardless
    of current membership - used to size the price-download universe."""
    if is_empty(df):
        return []
    return sorted(df["ticker"].unique().tolist())


def get_snapshot(df: pd.DataFrame, as_of_date) -> pd.DataFrame:
    """Return the [ticker, shares_outstanding, iwf] rows applicable on
    as_of_date, restricted to stocks that were NIFTY 50 members on that date.

    Returns an empty DataFrame (not fabricated defaults) if there is no
    applicable data.
    """
    if is_empty(df):
        return pd.DataFrame(columns=["ticker", "shares_outstanding", "iwf"])

    as_of = pd.Timestamp(as_of_date)
    eff_to = df["effective_to"].fillna(_FAR_FUTURE)
    mem_to = df["member_to"].fillna(_FAR_FUTURE)

    mask = (
        (df["effective_from"] <= as_of)
        & (eff_to >= as_of)
        & (df["member_from"] <= as_of)
        & (mem_to >= as_of)
    )
    snapshot = df.loc[mask, ["ticker", "shares_outstanding", "iwf"]].drop_duplicates(
        subset="ticker", keep="last"
    )
    return snapshot.reset_index(drop=True)


def _format_date_col(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series)
    return dt.apply(lambda v: "" if pd.isna(v) else v.strftime("%Y-%m-%d"))


def load_published_weights(path=None) -> pd.Series:
    """Optional: published/reference NIFTY weights for comparison against the
    calculated weight. Returns an empty Series if the file has no data rows
    (this is expected until the user supplies a verified source) - the
    Constituent Table shows N/A for this column rather than fabricating it.
    """
    if path is None:
        path = config.PUBLISHED_WEIGHTS_PATH
        if not path.exists():
            return pd.Series(dtype=float)
    df = pd.read_csv(path, comment="#", dtype=str)
    df = df.dropna(how="all")
    if df.empty:
        return pd.Series(dtype=float)
    df["ticker"] = df["ticker"].str.strip()
    df["weight_pct"] = pd.to_numeric(df["weight_pct"], errors="raise")
    return df.set_index("ticker")["weight_pct"]


def save_constituents(df: pd.DataFrame, path=None) -> None:
    path = path or config.CONSTITUENTS_PATH
    out = df.copy()
    for col in ["effective_from", "effective_to", "member_from", "member_to"]:
        out[col] = _format_date_col(out[col])
    out.to_csv(path, index=False, columns=CONSTITUENT_COLUMNS)
