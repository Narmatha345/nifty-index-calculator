import numpy as np
import pandas as pd
import pytest

from nifty_calc import engine


def test_build_close_panel_combines_tickers_and_drops_empty():
    price_dict = {
        "A.NS": pd.DataFrame({"Close": [10.0, 11.0]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"])),
        "B.NS": pd.DataFrame({"Close": [20.0, 21.0]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"])),
        "EMPTY.NS": pd.DataFrame(),
    }
    panel = engine.build_close_panel(price_dict)
    assert list(panel.columns) == ["A.NS", "B.NS"]
    assert panel.loc["2026-01-02", "B.NS"] == 21.0


def _weights_history():
    return pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-01-31", "2026-01-31", "2026-02-28", "2026-02-28"]),
            "ticker": ["A.NS", "B.NS", "A.NS", "B.NS"],
            "company_name": ["A", "B", "A", "B"],
            "industry": ["X", "Y", "X", "Y"],
            "weight_pct": [60.0, 40.0, 50.0, 50.0],
        }
    )


def test_build_weight_panel_holds_weight_constant_until_next_snapshot():
    dates = pd.date_range("2026-01-15", "2026-03-05", freq="D")
    panel = engine.build_weight_panel(_weights_history(), dates)

    # Before Jan 31 snapshot: no weight yet (not fabricated).
    assert pd.isna(panel.loc["2026-01-20", "A.NS"])
    # Between Jan 31 and Feb 28: Jan snapshot applies.
    assert panel.loc["2026-02-10", "A.NS"] == 60.0
    # From Feb 28 onward: Feb snapshot applies.
    assert panel.loc["2026-03-01", "A.NS"] == 50.0


def test_build_static_weight_panel_holds_one_vector_across_all_dates():
    weight_series = pd.Series({"A.NS": 60.0, "B.NS": 40.0})
    dates = pd.to_datetime(["2026-01-01", "2026-06-01", "2026-09-28"])

    panel = engine.build_static_weight_panel(weight_series, dates)

    assert list(panel.columns) == ["A.NS", "B.NS"]
    assert (panel["A.NS"] == 60.0).all()
    assert (panel["B.NS"] == 40.0).all()
    assert len(panel) == 3


def test_compute_raw_weighted_series_and_coverage():
    dates = pd.to_datetime(["2026-02-28", "2026-03-02"])
    close_panel = pd.DataFrame({"A.NS": [100.0, 110.0], "B.NS": [200.0, np.nan]}, index=dates)
    weight_panel = pd.DataFrame({"A.NS": [50.0, 50.0], "B.NS": [50.0, 50.0]}, index=dates)

    raw, coverage = engine.compute_raw_weighted_series(close_panel, weight_panel)

    assert raw.loc[dates[0]] == pytest.approx(100 * 0.5 + 200 * 0.5)
    assert coverage.loc[dates[0]] == pytest.approx(100.0)
    # B.NS missing a price on the second date: excluded, coverage drops.
    assert raw.loc[dates[1]] == pytest.approx(110 * 0.5)
    assert coverage.loc[dates[1]] == pytest.approx(50.0)


def test_calibrate_baseline_computes_factor_from_nearest_prior_trading_day():
    dates = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    raw = pd.Series([1000.0, 1010.0, 1020.0], index=dates)
    official = pd.Series([25000.0, 25200.0, 25400.0], index=dates)

    result = engine.calibrate_baseline(raw, official, "2026-01-06")

    assert result["baseline_date_used"] == pd.Timestamp("2026-01-06")
    assert result["normalization_factor"] == pytest.approx(25200.0 / 1010.0)


def test_calibrate_baseline_falls_back_to_next_trading_day_when_baseline_precedes_all_data():
    raw = pd.Series([1000.0, 1010.0], index=pd.to_datetime(["2026-05-04", "2026-05-05"]))
    official = pd.Series([25000.0, 25200.0], index=pd.to_datetime(["2026-05-04", "2026-05-05"]))

    result = engine.calibrate_baseline(raw, official, "2026-05-03")

    assert result["baseline_date_used"] == pd.Timestamp("2026-05-04")
    assert result["normalization_factor"] == pytest.approx(25.0)


def test_calibrate_baseline_raises_when_no_overlap_at_all():
    raw = pd.Series([1000.0], index=pd.to_datetime(["2026-01-01"]))
    official = pd.Series([25000.0], index=pd.to_datetime(["2026-02-01"]))
    with pytest.raises(ValueError):
        engine.calibrate_baseline(raw, official, "2026-01-15")


def test_compute_calculated_series_applies_constant_factor():
    raw = pd.Series([1000.0, 1010.0])
    calculated = engine.compute_calculated_series(raw, 25.0)
    assert list(calculated) == [25000.0, 25250.0]


def test_discrepancy_metrics_reports_current_max_mean_rmse():
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    calculated = pd.Series([100.0, 105.0, 90.0, 102.0], index=dates)
    official = pd.Series([100.0, 100.0, 100.0, 100.0], index=dates)

    metrics = engine.discrepancy_metrics(calculated, official)

    assert metrics["n_observations"] == 4
    assert metrics["current_diff"] == pytest.approx(2.0)
    assert metrics["max_abs_diff"] == pytest.approx(10.0)
    assert metrics["max_abs_diff_date"] == dates[2]
    assert metrics["mean_abs_diff"] == pytest.approx((0 + 5 + 10 + 2) / 4)
    assert metrics["rmse"] == pytest.approx(np.sqrt((0**2 + 5**2 + 10**2 + 2**2) / 4))


def test_discrepancy_metrics_empty_when_no_overlap():
    metrics = engine.discrepancy_metrics(pd.Series(dtype=float), pd.Series(dtype=float))
    assert metrics["n_observations"] == 0
    assert metrics["current_diff"] is None


def test_flag_large_deviations_only_returns_dates_above_threshold():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    calculated = pd.Series([100.0, 103.0, 100.0], index=dates)
    official = pd.Series([100.0, 100.0, 100.0], index=dates)

    flagged = engine.flag_large_deviations(calculated, official, threshold_pct=1.0)

    assert len(flagged) == 1
    assert flagged.iloc[0]["date"] == dates[1]
