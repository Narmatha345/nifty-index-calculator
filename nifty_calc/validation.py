"""Checks whether there is enough official weight data to run the
discrepancy analysis for a given range/date, so the UI can show an honest
MISSING DATA state instead of silently computing with placeholders."""

from __future__ import annotations

import pandas as pd

from nifty_calc import weights
from nifty_calc.schemas import MissingDataReport


def check_readiness(weights_history: pd.DataFrame, missing_months: list[str] | None = None, as_of_date=None) -> MissingDataReport:
    missing: list[str] = []

    if weights.is_empty(weights_history):
        missing.append(
            "no official NIFTY 50 weight data available for this range - NSE Indices could not be "
            "reached and no verified weight CSV has been imported via the Reference Data Manager page"
        )
    elif missing_months:
        missing.append(
            f"{len(missing_months)} month(s) have no official weight data ({', '.join(missing_months[:6])}"
            f"{'...' if len(missing_months) > 6 else ''}) - NSE Indices could not be reached for them and "
            "no verified fallback CSV covers them"
        )

    if as_of_date is not None and not weights.is_empty(weights_history):
        snap = weights.get_weight_snapshot(weights_history, as_of_date)
        if snap.empty:
            missing.append(f"no official weight snapshot on or before {pd.Timestamp(as_of_date).date()}")

    return MissingDataReport(missing_fields=missing)
