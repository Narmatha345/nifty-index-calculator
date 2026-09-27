"""Checks whether there is enough reference data to run a calculation for a
given date, so the UI can show an honest MISSING DATA state instead of
silently computing with placeholders.
"""

from __future__ import annotations

import pandas as pd

from nifty_calc import divisor as divisor_mod
from nifty_calc import reference_data
from nifty_calc.schemas import MissingDataReport


def check_readiness(
    constituents_df: pd.DataFrame,
    divisor_df: pd.DataFrame,
    as_of_date=None,
) -> MissingDataReport:
    missing: list[str] = []

    if reference_data.is_empty(constituents_df):
        missing.append(
            "no constituent data loaded (data/reference/constituents.csv has no rows - "
            "import real shares outstanding / IWF / membership data via the Reference Data Manager page)"
        )
    if divisor_mod.is_empty(divisor_df):
        missing.append(
            "no divisor calibrated (data/reference/divisor_history.csv has no rows - "
            "calibrate a divisor via the Reference Data Manager page)"
        )

    if as_of_date is not None and not missing:
        snap = reference_data.get_snapshot(constituents_df, as_of_date)
        if snap.empty:
            missing.append(f"no constituents are effective/members as of {pd.Timestamp(as_of_date).date()}")
        if divisor_mod.get_divisor(divisor_df, as_of_date) is None:
            missing.append(f"no divisor covers {pd.Timestamp(as_of_date).date()}")

    return MissingDataReport(missing_fields=missing)
