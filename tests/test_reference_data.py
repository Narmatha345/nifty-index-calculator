import pandas as pd

from nifty_calc import reference_data
from nifty_calc.schemas import CONSTITUENT_COLUMNS


def _sample_df():
    rows = [
        # ABC.NS: shares/iwf changed on 2024-06-01, still a member
        {
            "ticker": "ABC.NS",
            "shares_outstanding": 1000,
            "iwf": 0.50,
            "effective_from": "2020-01-01",
            "effective_to": "2024-05-31",
            "member_from": "2015-01-01",
            "member_to": None,
        },
        {
            "ticker": "ABC.NS",
            "shares_outstanding": 1100,
            "iwf": 0.55,
            "effective_from": "2024-06-01",
            "effective_to": None,
            "member_from": "2015-01-01",
            "member_to": None,
        },
        # XYZ.NS: left the index on 2023-01-01
        {
            "ticker": "XYZ.NS",
            "shares_outstanding": 2000,
            "iwf": 0.75,
            "effective_from": "2010-01-01",
            "effective_to": None,
            "member_from": "2010-01-01",
            "member_to": "2023-01-01",
        },
    ]
    df = pd.DataFrame(rows)
    for col in ["effective_from", "effective_to", "member_from", "member_to"]:
        df[col] = pd.to_datetime(df[col])
    return df


def test_is_empty_on_template_only_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text(",".join(CONSTITUENT_COLUMNS) + "\n# just a comment row\n")
    df = reference_data.load_constituents(p)
    assert reference_data.is_empty(df)
    assert reference_data.get_snapshot(df, "2024-01-01").empty
    assert reference_data.all_tickers(df) == []


def test_get_snapshot_picks_correct_effective_period():
    df = _sample_df()

    before = reference_data.get_snapshot(df, "2023-01-01")
    row = before[before["ticker"] == "ABC.NS"].iloc[0]
    assert row["shares_outstanding"] == 1000
    assert row["iwf"] == 0.50

    after = reference_data.get_snapshot(df, "2024-07-01")
    row = after[after["ticker"] == "ABC.NS"].iloc[0]
    assert row["shares_outstanding"] == 1100
    assert row["iwf"] == 0.55


def test_get_snapshot_excludes_non_members():
    df = _sample_df()
    snap = reference_data.get_snapshot(df, "2024-01-01")
    assert "XYZ.NS" not in snap["ticker"].values

    snap_earlier = reference_data.get_snapshot(df, "2015-01-01")
    assert "XYZ.NS" in snap_earlier["ticker"].values


def test_all_tickers_includes_departed_members():
    df = _sample_df()
    assert set(reference_data.all_tickers(df)) == {"ABC.NS", "XYZ.NS"}


def test_validate_constituents_rejects_blank_shares_and_iwf(tmp_path):
    """Simulates uploading a seed CSV (tickers filled, shares/iwf left blank for
    the user to complete) via the Reference Data Manager - every incomplete row
    must be rejected, not silently pass through as NaN."""
    p = tmp_path / "seed.csv"
    p.write_text(
        ",".join(CONSTITUENT_COLUMNS) + "\n"
        "ABC.NS,,,,,,\n"
        "XYZ.NS,1000,0.5,2024-01-01,,2020-01-01,\n"
    )
    df = reference_data.load_constituents(p)
    errors = reference_data.validate_constituents(df)
    assert len(errors) == 1
    assert "ABC.NS" in errors[0]
    assert "shares_outstanding" in errors[0]
