"""Data schemas for time-varying reference data (constituents, divisor history).

These describe the required columns/types for the CSV files in data/reference/.
No real financial values live in this module - it only defines shape and
validation, never sample data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


def _is_nan(value: float) -> bool:
    try:
        return math.isnan(value)
    except TypeError:
        return False


CONSTITUENT_COLUMNS = [
    "ticker",
    "shares_outstanding",
    "iwf",
    "effective_from",
    "effective_to",
    "member_from",
    "member_to",
]

DIVISOR_COLUMNS = [
    "effective_from",
    "effective_to",
    "divisor",
    "reason",
    "calibrated_at",
    "calibration_source",
]


@dataclass(frozen=True)
class ConstituentRow:
    ticker: str
    shares_outstanding: float
    iwf: float
    effective_from: date
    effective_to: date | None
    member_from: date
    member_to: date | None

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker must not be empty")
        if self.shares_outstanding is None or _is_nan(self.shares_outstanding):
            raise ValueError("shares_outstanding is required and must not be blank")
        if self.shares_outstanding <= 0:
            raise ValueError(f"shares_outstanding must be positive, got {self.shares_outstanding}")
        if self.iwf is None or _is_nan(self.iwf):
            raise ValueError("iwf is required and must not be blank")
        if not (0 < self.iwf <= 1):
            raise ValueError(f"iwf must be a fraction in (0, 1], got {self.iwf}")
        if self.effective_from is None:
            raise ValueError("effective_from is required and must not be blank")
        if self.member_from is None:
            raise ValueError("member_from is required and must not be blank")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")
        if self.member_to is not None and self.member_to < self.member_from:
            raise ValueError("member_to must not be before member_from")


@dataclass(frozen=True)
class DivisorRow:
    effective_from: date
    effective_to: date | None
    divisor: float
    reason: str
    calibrated_at: str
    calibration_source: str

    def __post_init__(self) -> None:
        if self.divisor is None or _is_nan(self.divisor):
            raise ValueError("divisor is required and must not be blank")
        if self.divisor <= 0:
            raise ValueError(f"divisor must be positive, got {self.divisor}")
        if self.effective_from is None:
            raise ValueError("effective_from is required and must not be blank")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be before effective_from")


class ValidationError(Exception):
    """Raised when reference data fails schema validation."""


@dataclass
class MissingDataReport:
    """Describes what reference data is missing/insufficient for a request."""

    missing_fields: list[str]

    @property
    def is_missing(self) -> bool:
        return len(self.missing_fields) > 0

    def as_banner_text(self) -> str:
        if not self.is_missing:
            return ""
        return "MISSING DATA: " + "; ".join(self.missing_fields)
