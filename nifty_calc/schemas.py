"""Shared small types for the reference-data layer. No real financial values
live in this module - it only defines shape, never sample data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MissingDataReport:
    """Describes what's missing/insufficient for a requested calculation."""

    missing_fields: list[str]

    @property
    def is_missing(self) -> bool:
        return len(self.missing_fields) > 0

    def as_banner_text(self) -> str:
        if not self.is_missing:
            return ""
        return "MISSING DATA: " + "; ".join(self.missing_fields)
