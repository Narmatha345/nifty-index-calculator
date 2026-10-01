import pandas as pd
import pytest

from nifty_calc import corporate_actions, engine


def _close(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": list(values.values())}, index=pd.to_datetime(list(values)))


def test_price_sources_maps_renamed_and_merged_symbols_and_skips_dummies():
    sources = corporate_actions.price_sources(
        ["TATAMOTORS.NS", "ZOMATO.NS", "LTIM.NS", "HDFC.NS", "HDFCBANK.NS", "DUMMYTATAM.NS", "INFY.NS"]
    )
    assert sources == ["ETERNAL.NS", "HDFCBANK.NS", "INFY.NS", "LTM.NS", "TMPV.NS"]


def test_aliased_ticker_is_priced_from_its_current_symbol():
    price_dict = {"ETERNAL.NS": _close({"2025-03-28": 200.0, "2025-04-01": 210.0})}
    panel = corporate_actions.build_constituent_close_panel(["ZOMATO.NS"], price_dict, "2025-03-28")
    assert list(panel.columns) == ["ZOMATO.NS"]
    assert panel.loc["2025-04-01", "ZOMATO.NS"] == 210.0


def test_demerger_parent_keeps_spun_off_value_when_weights_predate_ex_date():
    # Real Tata Motors closes around the 14-Oct-2025 demerger (Yahoo doesn't
    # adjust for it): 660.75 -> 400 is the CV business leaving, not a 39% fall.
    price_dict = {"TMPV.NS": _close({"2025-10-13": 660.75, "2025-10-14": 395.45})}
    panel = corporate_actions.build_constituent_close_panel(["TATAMOTORS.NS"], price_dict, "2025-09-30")
    assert panel.loc["2025-10-13", "TATAMOTORS.NS"] == pytest.approx(660.75)
    assert panel.loc["2025-10-14", "TATAMOTORS.NS"] == pytest.approx(395.45 + 260.75)


def test_demerger_parent_excludes_spun_off_value_when_weights_postdate_ex_date():
    price_dict = {"TMPV.NS": _close({"2025-10-13": 660.75, "2025-10-14": 395.45, "2025-10-31": 410.0})}
    panel = corporate_actions.build_constituent_close_panel(["TMPV.NS", "DUMMYTATAM.NS"], price_dict, "2025-10-31")
    assert panel.loc["2025-10-13", "TMPV.NS"] == pytest.approx(660.75 - 260.75)
    assert panel.loc["2025-10-31", "TMPV.NS"] == pytest.approx(410.0)
    # NSE holds the dummy at a constant price.
    assert (panel["DUMMYTATAM.NS"] == 260.75).all()


def test_demerger_ex_date_causes_no_jump_in_the_calculated_index():
    price_dict = {
        "TMPV.NS": _close({"2025-09-30": 670.0, "2025-10-13": 660.75, "2025-10-14": 400.0}),
        "INFY.NS": _close({"2025-09-30": 1500.0, "2025-10-13": 1500.0, "2025-10-14": 1500.0}),
    }
    weight_series = pd.Series({"TATAMOTORS.NS": 50.0, "INFY.NS": 50.0})
    panel = corporate_actions.build_constituent_close_panel(list(weight_series.index), price_dict, "2025-09-30")
    anchor = engine.anchor_prices(panel, "2025-09-30")
    raw, _ = engine.compute_raw_weighted_series(panel, engine.build_static_weight_panel(weight_series, panel.index), anchor)
    # Price-discovery price == prev close - dummy value, so no move on the ex-date.
    assert raw.loc["2025-10-14"] == pytest.approx(raw.loc["2025-10-13"])


def test_zero_volume_placeholder_bar_is_treated_as_missing():
    df = pd.DataFrame(
        {"Close": [1238.85, 1238.85, 1247.15], "Volume": [16640917, 0, 16162399]},
        index=pd.to_datetime(["2025-03-17", "2025-03-18", "2025-03-19"]),
    )
    panel = corporate_actions.build_constituent_close_panel(["RELIANCE.NS"], {"RELIANCE.NS": df}, "2025-03-17")
    assert pd.isna(panel.loc["2025-03-18", "RELIANCE.NS"])
    assert panel.loc["2025-03-19", "RELIANCE.NS"] == 1247.15


def test_constituent_with_no_price_data_is_dropped():
    panel = corporate_actions.build_constituent_close_panel(
        ["INFY.NS", "NOPRICE.NS"], {"INFY.NS": _close({"2026-01-02": 1500.0})}, "2026-01-02"
    )
    assert list(panel.columns) == ["INFY.NS"]
