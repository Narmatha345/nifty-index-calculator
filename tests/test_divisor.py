import pandas as pd

from nifty_calc import divisor


def _sample_df():
    rows = [
        {
            "effective_from": "2020-01-01",
            "effective_to": "2023-12-31",
            "divisor": 1000.0,
            "reason": "initial calibration",
            "calibrated_at": "2020-01-01 10:00",
            "calibration_source": "test",
        },
        {
            "effective_from": "2024-01-01",
            "effective_to": None,
            "divisor": 1050.0,
            "reason": "constituent change",
            "calibrated_at": "2024-01-01 10:00",
            "calibration_source": "test",
        },
    ]
    df = pd.DataFrame(rows)
    df["effective_from"] = pd.to_datetime(df["effective_from"])
    df["effective_to"] = pd.to_datetime(df["effective_to"])
    return df


def test_get_divisor_empty_returns_none(tmp_path):
    empty = pd.DataFrame(columns=["effective_from", "effective_to", "divisor"])
    assert divisor.get_divisor(empty, "2024-01-01") is None


def test_get_divisor_picks_correct_period():
    df = _sample_df()
    assert divisor.get_divisor(df, "2022-06-01") == 1000.0
    assert divisor.get_divisor(df, "2024-06-01") == 1050.0


def test_get_divisor_no_coverage_returns_none():
    df = _sample_df()
    assert divisor.get_divisor(df, "2019-01-01") is None


def test_calibrate_divisor_formula():
    # total_ffmc / official_index_value
    assert divisor.calibrate_divisor(total_ffmc=25_000_000.0, official_index_value=25000.0) == 1000.0


def test_append_divisor_row_closes_prior_open_row():
    df = _sample_df()
    # make the last row open-ended already (it is), append a new one starting later
    updated = divisor.append_divisor_row(
        df,
        effective_from=pd.Timestamp("2025-01-01"),
        divisor=1100.0,
        reason="test append",
        calibrated_at="2025-01-01 09:00",
        calibration_source="test",
    )
    prior = updated[updated["divisor"] == 1050.0].iloc[0]
    assert prior["effective_to"] == pd.Timestamp("2024-12-31")
    newest = updated[updated["divisor"] == 1100.0].iloc[0]
    assert pd.isna(newest["effective_to"])
