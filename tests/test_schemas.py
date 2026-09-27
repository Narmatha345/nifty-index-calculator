import datetime

import pytest

from nifty_calc.schemas import ConstituentRow, DivisorRow


def _valid_constituent_kwargs():
    return dict(
        ticker="ABC.NS",
        shares_outstanding=1000.0,
        iwf=0.5,
        effective_from=datetime.date(2024, 1, 1),
        effective_to=None,
        member_from=datetime.date(2020, 1, 1),
        member_to=None,
    )


def test_constituent_row_accepts_valid_data():
    ConstituentRow(**_valid_constituent_kwargs())  # must not raise


def test_constituent_row_rejects_nan_shares_outstanding():
    kwargs = _valid_constituent_kwargs() | {"shares_outstanding": float("nan")}
    with pytest.raises(ValueError, match="shares_outstanding"):
        ConstituentRow(**kwargs)


def test_constituent_row_rejects_nan_iwf():
    kwargs = _valid_constituent_kwargs() | {"iwf": float("nan")}
    with pytest.raises(ValueError, match="iwf"):
        ConstituentRow(**kwargs)


def test_constituent_row_rejects_blank_effective_from():
    kwargs = _valid_constituent_kwargs() | {"effective_from": None}
    with pytest.raises(ValueError, match="effective_from"):
        ConstituentRow(**kwargs)


def test_constituent_row_rejects_blank_member_from():
    kwargs = _valid_constituent_kwargs() | {"member_from": None}
    with pytest.raises(ValueError, match="member_from"):
        ConstituentRow(**kwargs)


def _valid_divisor_kwargs():
    return dict(
        effective_from=datetime.date(2024, 1, 1),
        effective_to=None,
        divisor=1000.0,
        reason="initial calibration",
        calibrated_at="2024-01-01 10:00",
        calibration_source="test",
    )


def test_divisor_row_accepts_valid_data():
    DivisorRow(**_valid_divisor_kwargs())  # must not raise


def test_divisor_row_rejects_nan_divisor():
    kwargs = _valid_divisor_kwargs() | {"divisor": float("nan")}
    with pytest.raises(ValueError, match="divisor"):
        DivisorRow(**kwargs)


def test_divisor_row_rejects_blank_effective_from():
    kwargs = _valid_divisor_kwargs() | {"effective_from": None}
    with pytest.raises(ValueError, match="effective_from"):
        DivisorRow(**kwargs)
