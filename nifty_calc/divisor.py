"""Divisor history: the value(s) that convert total free-float market cap into
an index level, over time.

Never guesses a divisor. If no calibrated divisor is on file for a requested
date, get_divisor() returns None so callers can show a MISSING DATA state.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

import config
from nifty_calc.schemas import DIVISOR_COLUMNS, DivisorRow

_FAR_FUTURE = pd.Timestamp.max.normalize()


def load_divisor_history(path=None) -> pd.DataFrame:
    path = path or config.DIVISOR_HISTORY_PATH
    df = pd.read_csv(path, comment="#", dtype=str)
    df = df.dropna(how="all")
    if df.empty:
        return pd.DataFrame(columns=DIVISOR_COLUMNS)

    df["divisor"] = pd.to_numeric(df["divisor"], errors="raise")
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    df["effective_to"] = pd.to_datetime(df["effective_to"])
    df["reason"] = df["reason"].fillna("")
    df["calibrated_at"] = df["calibrated_at"].fillna("")
    df["calibration_source"] = df["calibration_source"].fillna("")
    return df.sort_values("effective_from").reset_index(drop=True)


def validate_divisor_history(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    for i, row in df.iterrows():
        try:
            DivisorRow(
                effective_from=_to_date(row["effective_from"]),
                effective_to=_to_date(row["effective_to"]),
                divisor=float(row["divisor"]),
                reason=str(row.get("reason", "")),
                calibrated_at=str(row.get("calibrated_at", "")),
                calibration_source=str(row.get("calibration_source", "")),
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"row {i}: {exc}")
    return errors


def _to_date(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date()


def is_empty(df: pd.DataFrame) -> bool:
    return df is None or len(df) == 0


def get_divisor(df: pd.DataFrame, as_of_date) -> float | None:
    """Return the divisor applicable on as_of_date, or None if no calibrated
    divisor covers that date."""
    if is_empty(df):
        return None

    as_of = pd.Timestamp(as_of_date)
    eff_to = df["effective_to"].fillna(_FAR_FUTURE)
    mask = (df["effective_from"] <= as_of) & (eff_to >= as_of)
    matches = df.loc[mask]
    if matches.empty:
        return None
    return float(matches.iloc[-1]["divisor"])


def calibrate_divisor(total_ffmc: float, official_index_value: float) -> float:
    """Compute a divisor: Sum(Price*Shares*IWF) / Official Index Value.

    This is a pure arithmetic helper - callers decide when calibration is
    appropriate (see engine.calibrate_divisor for the FFMC computation) and
    are responsible for persisting the result as a new divisor_history row
    via append_divisor_row(). This function does not write to disk and does
    not get called automatically/repeatedly - calibration is a deliberate,
    one-time (or corporate-action-triggered) action.
    """
    if official_index_value <= 0:
        raise ValueError("official_index_value must be positive")
    return total_ffmc / official_index_value


def append_divisor_row(
    df: pd.DataFrame,
    effective_from: _dt.date,
    divisor: float,
    reason: str,
    calibrated_at: str,
    calibration_source: str,
) -> pd.DataFrame:
    """Close out any open-ended prior row as of the day before effective_from,
    then append the new row. Returns the updated DataFrame (caller persists
    it via save_divisor_history)."""
    out = df.copy()
    new_from = pd.Timestamp(effective_from)

    if not is_empty(out):
        open_mask = out["effective_to"].isna()
        prior_mask = open_mask & (out["effective_from"] < new_from)
        if prior_mask.any():
            out.loc[prior_mask, "effective_to"] = new_from - pd.Timedelta(days=1)

    new_row = pd.DataFrame(
        [
            {
                "effective_from": new_from,
                "effective_to": pd.NaT,
                "divisor": divisor,
                "reason": reason,
                "calibrated_at": calibrated_at,
                "calibration_source": calibration_source,
            }
        ]
    )
    return pd.concat([out, new_row], ignore_index=True).sort_values("effective_from").reset_index(drop=True)


def _format_date_col(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series)
    return dt.apply(lambda v: "" if pd.isna(v) else v.strftime("%Y-%m-%d"))


def save_divisor_history(df: pd.DataFrame, path=None) -> None:
    path = path or config.DIVISOR_HISTORY_PATH
    out = df.copy()
    for col in ["effective_from", "effective_to"]:
        out[col] = _format_date_col(out[col])
    out.to_csv(path, index=False, columns=DIVISOR_COLUMNS)
