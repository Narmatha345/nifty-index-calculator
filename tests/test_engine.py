import math

import pandas as pd
import pytest

from nifty_calc import engine


def _constituents_ref():
    rows = [
        {
            "ticker": "A.NS",
            "shares_outstanding": 100,
            "iwf": 0.5,
            "effective_from": "2024-01-01",
            "effective_to": None,
            "member_from": "2024-01-01",
            "member_to": None,
        },
        {
            "ticker": "B.NS",
            "shares_outstanding": 200,
            "iwf": 0.25,
            "effective_from": "2024-01-01",
            "effective_to": None,
            "member_from": "2024-01-01",
            "member_to": None,
        },
    ]
    df = pd.DataFrame(rows)
    for col in ["effective_from", "effective_to", "member_from", "member_to"]:
        df[col] = pd.to_datetime(df[col])
    return df


def _divisor_ref():
    df = pd.DataFrame(
        [{"effective_from": "2024-01-01", "effective_to": None, "divisor": 10.0}]
    )
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    df["effective_to"] = pd.to_datetime(df["effective_to"])
    return df


def _close_panel():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {"A.NS": [10.0, 12.0, 11.0], "B.NS": [20.0, 19.0, 21.0]}, index=dates
    )


def test_compute_ffmc():
    price = pd.Series({"A.NS": 10.0, "B.NS": 20.0})
    shares = pd.Series({"A.NS": 100.0, "B.NS": 200.0})
    iwf = pd.Series({"A.NS": 0.5, "B.NS": 0.25})
    ffmc = engine.compute_ffmc(price, shares, iwf)
    assert ffmc["A.NS"] == pytest.approx(500.0)
    assert ffmc["B.NS"] == pytest.approx(1000.0)


def test_compute_index_value():
    assert engine.compute_index_value(1500.0, 10.0) == pytest.approx(150.0)
    with pytest.raises(ValueError):
        engine.compute_index_value(1500.0, 0)


def test_reconstruct_series_matches_hand_calc():
    result = engine.reconstruct_series(
        _close_panel().index, _close_panel(), _constituents_ref(), _divisor_ref()
    )
    expected = [150.0, 155.0, 160.0]
    assert result["calculated"].tolist() == pytest.approx(expected)


def test_snapshot_at_matches_hand_calc():
    snap = engine.snapshot_at("2024-01-02", _constituents_ref(), _divisor_ref(), _close_panel())
    a = snap[snap["ticker"] == "A.NS"].iloc[0]
    b = snap[snap["ticker"] == "B.NS"].iloc[0]

    assert a["free_float_market_cap"] == pytest.approx(600.0)
    assert b["free_float_market_cap"] == pytest.approx(950.0)
    assert a["calculated_weight_pct"] == pytest.approx(600 / 1550 * 100)
    assert b["calculated_weight_pct"] == pytest.approx(950 / 1550 * 100)
    assert a["price_change_pct"] == pytest.approx(20.0)
    assert b["price_change_pct"] == pytest.approx(-5.0)
    assert a["point_contribution"] == pytest.approx(60.0)
    assert b["point_contribution"] == pytest.approx(95.0)


def test_contribution_analysis_reconciles_to_index_change():
    contrib = engine.contribution_analysis(
        "2024-01-01", "2024-01-03", _close_panel(), _constituents_ref(), _divisor_ref()
    )
    series = engine.reconstruct_series(
        _close_panel().index, _close_panel(), _constituents_ref(), _divisor_ref()
    )
    index_change = series["calculated"].iloc[-1] - series["calculated"].iloc[0]
    assert contrib["point_contribution"].sum() == pytest.approx(index_change)

    a_contrib = contrib[contrib["ticker"] == "A.NS"]["point_contribution"].iloc[0]
    b_contrib = contrib[contrib["ticker"] == "B.NS"]["point_contribution"].iloc[0]
    assert a_contrib == pytest.approx(5.0)
    assert b_contrib == pytest.approx(5.0)


def test_accuracy_metrics_hand_calc():
    calculated = pd.Series([150.0, 155.0, 160.0])
    official = pd.Series([151.0, 154.0, 162.0])
    metrics = engine.accuracy_metrics(calculated, official)

    assert metrics["current_error"] == pytest.approx(-2.0)
    assert metrics["mean_absolute_error"] == pytest.approx(4 / 3)
    assert metrics["rmse"] == pytest.approx(math.sqrt(2))
    assert metrics["max_error"] == pytest.approx(2.0)
    assert metrics["n_observations"] == 3


def test_accuracy_metrics_empty_returns_none_not_zero():
    metrics = engine.accuracy_metrics(pd.Series(dtype=float), pd.Series(dtype=float))
    assert metrics["current_error"] is None
    assert metrics["n_observations"] == 0


def test_missing_divisor_gives_empty_snapshot_not_placeholder():
    empty_divisor = pd.DataFrame(columns=["effective_from", "effective_to", "divisor"])
    snap = engine.snapshot_at("2024-01-02", _constituents_ref(), empty_divisor, _close_panel())
    assert snap.empty


def test_reconstruct_series_uses_divisor_applicable_on_each_date():
    """A divisor change mid-range must be picked up day-by-day, not applied
    retroactively or held over from the start of the range."""
    close_panel = _close_panel()
    divisor_ref = pd.DataFrame(
        [
            {"effective_from": "2024-01-01", "effective_to": "2024-01-02", "divisor": 10.0},
            {"effective_from": "2024-01-03", "effective_to": None, "divisor": 20.0},
        ]
    )
    divisor_ref["effective_from"] = pd.to_datetime(divisor_ref["effective_from"])
    divisor_ref["effective_to"] = pd.to_datetime(divisor_ref["effective_to"])

    result = engine.reconstruct_series(close_panel.index, close_panel, _constituents_ref(), divisor_ref)
    # 2024-01-01 & 01-02 use divisor 10 (as in the base fixture); 01-03 switches to divisor 20.
    expected = [150.0, 155.0, 80.0]  # total ffmc on 01-03 is 1600 -> 1600/20 = 80
    assert result["calculated"].tolist() == pytest.approx(expected)


def test_reconstruct_series_respects_membership_change_mid_range():
    """A stock joining/leaving mid-range must only be included in the total on
    the dates it was actually a NIFTY 50 member."""
    rows = [
        {
            "ticker": "A.NS",
            "shares_outstanding": 100,
            "iwf": 0.5,
            "effective_from": "2024-01-01",
            "effective_to": None,
            "member_from": "2024-01-01",
            "member_to": None,
        },
        {
            # B.NS leaves the index after 2024-01-02
            "ticker": "B.NS",
            "shares_outstanding": 200,
            "iwf": 0.25,
            "effective_from": "2024-01-01",
            "effective_to": None,
            "member_from": "2024-01-01",
            "member_to": "2024-01-02",
        },
    ]
    df = pd.DataFrame(rows)
    for col in ["effective_from", "effective_to", "member_from", "member_to"]:
        df[col] = pd.to_datetime(df[col])

    result = engine.reconstruct_series(_close_panel().index, _close_panel(), df, _divisor_ref())
    # 01-01, 01-02: both A+B included (same as base fixture: 150, 155)
    # 01-03: B.NS no longer a member -> only A.NS's ffmc (11*100*0.5=550) / 10 = 55.0
    expected = [150.0, 155.0, 55.0]
    assert result["calculated"].tolist() == pytest.approx(expected)


def test_calibrate_divisor_for_date_matches_hand_calc():
    result = engine.calibrate_divisor_for_date(
        "2024-01-02",
        _constituents_ref(),
        _close_panel(),
        official_series=pd.Series({pd.Timestamp("2024-01-02"): 155.0}),
    )
    assert result["use_date"] == pd.Timestamp("2024-01-02")
    assert result["total_ffmc"] == pytest.approx(1550.0)
    assert result["official_value"] == pytest.approx(155.0)
    assert result["divisor"] == pytest.approx(10.0)
    assert result["tickers_used"] == 2
    assert result["tickers_total"] == 2


def test_calibrate_divisor_for_date_falls_back_to_prior_trading_day():
    """Requesting calibration on a non-trading day (e.g. weekend/holiday) must
    fall back to the latest available trading day on or before it."""
    result = engine.calibrate_divisor_for_date(
        "2024-01-05",  # a Friday with no data in the fixture; latest available is 01-03
        _constituents_ref(),
        _close_panel(),
        official_series=pd.Series(
            {pd.Timestamp("2024-01-01"): 150.0, pd.Timestamp("2024-01-03"): 160.0}
        ),
    )
    assert result["use_date"] == pd.Timestamp("2024-01-03")


def test_calibrate_divisor_for_date_uses_earlier_of_two_available_dates():
    """If constituent prices and the official index have different latest
    available dates, calibration must use the earlier (overlapping) one -
    never a mismatched combination from two different days."""
    result = engine.calibrate_divisor_for_date(
        "2024-01-03",
        _constituents_ref(),
        _close_panel(),  # constituent prices available through 01-03
        official_series=pd.Series({pd.Timestamp("2024-01-01"): 150.0}),  # official only through 01-01
    )
    assert result["use_date"] == pd.Timestamp("2024-01-01")
    assert result["official_value"] == pytest.approx(150.0)


def test_calibrate_divisor_for_date_raises_when_no_price_data():
    with pytest.raises(ValueError, match="No price data"):
        engine.calibrate_divisor_for_date(
            "2024-01-02", _constituents_ref(), pd.DataFrame(), pd.Series(dtype=float)
        )


def test_calibrate_divisor_for_date_raises_when_no_ticker_overlap():
    empty_constituents = _constituents_ref().iloc[0:0]
    with pytest.raises(ValueError, match="No overlap"):
        engine.calibrate_divisor_for_date(
            "2024-01-02",
            empty_constituents,
            _close_panel(),
            official_series=pd.Series({pd.Timestamp("2024-01-02"): 155.0}),
        )
