import pandas as pd
import pytest

import config
from nifty_calc import weights

_SAMPLE_CSV = """Annexure II-  Nifty 50 Index : August 2026,,,,,,,,,,,
,,,,,,,,,,,
Sr. No,Security Symbol,Security Name,Basic Industry,Equity Capital (In Rs.),Index Market Capitalisation (Rs. Crores),Weightage (%),Beta,R2,Volatility (%),Monthly Return,Avg. Impact Cost (%)
1,HDFCBANK,HDFC Bank Ltd.,Private Sector Bank,15400809456,1082671.03,9.85,1.25,0.62,0.80,-5.23,0.01
2,ICICIBANK,ICICI Bank Ltd.,Private Sector Bank,14347009720,1038686.53,9.45,0.93,0.41,1.06,1.30,0.02
3,RELIANCE,Reliance Industries Ltd.,Refineries & Marketing,135325387220,860281.87,7.83,0.93,0.35,1.12,-2.36,0.01
,,,,,2981639.43,,,,,,0.02
,,,,,,,,,,,
* Beta & R2 are calculated for the period 01-Sep-2025 to 31-Aug-2026,,,,,,,,,,,
,,,,,,,,,,,
*Last day of trading was 31-Aug-2026,,,,,,,,,,,
"""


def test_parse_mcwb_csv_extracts_rows_and_as_of_date():
    parsed = weights.parse_mcwb_csv(_SAMPLE_CSV, pd.Timestamp("2026-08-01"))

    assert list(parsed["ticker"]) == ["HDFCBANK.NS", "ICICIBANK.NS", "RELIANCE.NS"]
    assert list(parsed["weight_pct"]) == [9.85, 9.45, 7.83]
    assert (parsed["as_of_date"] == pd.Timestamp("2026-08-31")).all()
    assert list(parsed["industry"]) == ["Private Sector Bank", "Private Sector Bank", "Refineries & Marketing"]


def test_parse_mcwb_csv_falls_back_to_month_end_without_footer():
    text_without_footer = _SAMPLE_CSV.replace(
        "*Last day of trading was 31-Aug-2026,,,,,,,,,,,\n", ""
    )
    parsed = weights.parse_mcwb_csv(text_without_footer, pd.Timestamp("2026-08-01"))
    assert (parsed["as_of_date"] == pd.Timestamp("2026-08-31")).all()


def test_month_starts_between():
    result = weights.month_starts_between("2026-06-15", "2026-08-02")
    assert result == [pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-01"), pd.Timestamp("2026-08-01")]


def test_month_starts_between_clamps_to_earliest_available():
    result = weights.month_starts_between("1999-01-01", "1999-03-01")
    assert result == []


def _history_df():
    return pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(
                ["2026-06-30", "2026-06-30", "2026-07-31", "2026-07-31"]
            ),
            "ticker": ["HDFCBANK.NS", "RELIANCE.NS", "HDFCBANK.NS", "RELIANCE.NS"],
            "company_name": ["HDFC Bank", "Reliance", "HDFC Bank", "Reliance"],
            "industry": ["Bank", "Energy", "Bank", "Energy"],
            "weight_pct": [9.0, 8.0, 9.5, 7.5],
        }
    )


def test_get_weight_snapshot_uses_most_recent_prior_month():
    history = _history_df()
    snap = weights.get_weight_snapshot(history, "2026-07-15")
    assert snap.loc["HDFCBANK.NS", "weight_pct"] == 9.0
    assert (snap["as_of_date"] == pd.Timestamp("2026-06-30")).all()


def test_get_weight_snapshot_empty_before_earliest_data():
    history = _history_df()
    snap = weights.get_weight_snapshot(history, "2020-01-01")
    assert snap.empty


def test_get_history_fetches_one_lookback_month_before_start(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEIGHTS_CACHE_DIR", tmp_path)
    requested_months = []

    def fake_fetch(month_start, timeout=30):
        requested_months.append(month_start)
        return pd.DataFrame(
            {
                "as_of_date": [month_start + pd.offsets.MonthEnd(0)],
                "ticker": ["A.NS"],
                "company_name": ["A"],
                "industry": ["X"],
                "weight_pct": [10.0],
            }
        )

    monkeypatch.setattr(weights, "fetch_month_from_nse", fake_fetch)
    monkeypatch.setattr(weights, "load_reference_weights", lambda path=None: pd.DataFrame(columns=weights.HISTORY_COLUMNS))

    history, missing = weights.get_history("2026-03-01", "2026-03-31", use_network=True)

    assert pd.Timestamp("2026-02-01") in requested_months
    assert pd.Timestamp("2026-03-01") in requested_months
    assert missing == []


def test_load_uploaded_weights_csv_detects_raw_nse_format(tmp_path):
    p = tmp_path / "nifty50_mcwb.csv"
    p.write_text(_SAMPLE_CSV)

    parsed = weights.load_uploaded_weights_csv(p)

    assert list(parsed["ticker"]) == ["HDFCBANK.NS", "ICICIBANK.NS", "RELIANCE.NS"]
    assert (parsed["as_of_date"] == pd.Timestamp("2026-08-31")).all()


def test_load_uploaded_weights_csv_detects_normalized_schema(tmp_path):
    p = tmp_path / "already_normalized.csv"
    p.write_text(
        "as_of_date,ticker,company_name,industry,weight_pct\n"
        "2026-06-30,HDFCBANK.NS,HDFC Bank,Bank,9.5\n"
    )

    parsed = weights.load_uploaded_weights_csv(p)

    assert list(parsed["ticker"]) == ["HDFCBANK.NS"]
    assert parsed["weight_pct"].iloc[0] == 9.5


def test_load_uploaded_weights_csv_raises_on_raw_nse_format_without_footer(tmp_path):
    p = tmp_path / "nifty50_mcwb_no_footer.csv"
    p.write_text(_SAMPLE_CSV.replace("*Last day of trading was 31-Aug-2026,,,,,,,,,,,\n", ""))

    with pytest.raises(ValueError, match="Last day of trading"):
        weights.load_uploaded_weights_csv(p)


def test_load_uploaded_weights_csv_raises_on_unrecognized_format(tmp_path):
    p = tmp_path / "garbage.csv"
    p.write_text("foo,bar\n1,2\n")

    with pytest.raises(ValueError, match="Unrecognized CSV format"):
        weights.load_uploaded_weights_csv(p)


def test_format_period_label():
    assert weights.format_period_label(pd.Timestamp("2026-08-15")) == "August 2026"


def test_list_available_periods_combines_cache_and_reference(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "2026-06.csv").write_text("as_of_date,ticker,company_name,industry,weight_pct\n")
    (cache_dir / "2026-08.csv").write_text("as_of_date,ticker,company_name,industry,weight_pct\n")
    monkeypatch.setattr(config, "WEIGHTS_CACHE_DIR", cache_dir)

    reference_df = pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-07-31"]),
            "ticker": ["A.NS"],
            "company_name": ["A"],
            "industry": ["X"],
            "weight_pct": [10.0],
        }
    )
    monkeypatch.setattr(weights, "load_reference_weights", lambda path=None: reference_df)

    result = weights.list_available_periods()

    assert result == [pd.Timestamp("2026-08-01"), pd.Timestamp("2026-07-01"), pd.Timestamp("2026-06-01")]


def test_get_weight_period_uses_cache_without_network(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cached = pd.DataFrame(
        {
            "as_of_date": ["2026-08-31"],
            "ticker": ["A.NS"],
            "company_name": ["A"],
            "industry": ["X"],
            "weight_pct": [10.0],
        }
    )
    cached.to_csv(cache_dir / "2026-08.csv", index=False)
    monkeypatch.setattr(config, "WEIGHTS_CACHE_DIR", cache_dir)

    def fail_if_called(month_start, timeout=30):
        raise AssertionError("should not hit the network when cache already has this month")

    monkeypatch.setattr(weights, "fetch_month_from_nse", fail_if_called)

    result = weights.get_weight_period(pd.Timestamp("2026-08-05"), use_network=True)

    assert list(result["ticker"]) == ["A.NS"]


def test_get_weight_period_falls_back_to_reference_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEIGHTS_CACHE_DIR", tmp_path / "empty_cache")
    reference_df = pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-07-31"]),
            "ticker": ["B.NS"],
            "company_name": ["B"],
            "industry": ["Y"],
            "weight_pct": [5.0],
        }
    )
    monkeypatch.setattr(weights, "load_reference_weights", lambda path=None: reference_df)

    result = weights.get_weight_period(pd.Timestamp("2026-07-01"), use_network=False)

    assert list(result["ticker"]) == ["B.NS"]


def test_get_weight_period_returns_empty_when_truly_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEIGHTS_CACHE_DIR", tmp_path / "empty_cache")
    monkeypatch.setattr(weights, "load_reference_weights", lambda path=None: pd.DataFrame(columns=weights.HISTORY_COLUMNS))

    result = weights.get_weight_period(pd.Timestamp("2026-09-01"), use_network=False)

    assert result.empty


def test_validate_reference_weights_rejects_bad_rows():
    df = pd.DataFrame(
        [
            {"ticker": "HDFCBANK.NS", "weight_pct": 9.5, "as_of_date": pd.Timestamp("2026-06-30")},
            {"ticker": "", "weight_pct": 5.0, "as_of_date": pd.Timestamp("2026-06-30")},
            {"ticker": "BAD.NS", "weight_pct": 150.0, "as_of_date": pd.Timestamp("2026-06-30")},
        ]
    )
    errors = weights.validate_reference_weights(df)
    assert len(errors) == 2
