"""Constituent Table: per-stock price, shares, IWF, free-float market cap,
calculated weight, price change, and NIFTY point contribution, as of a
selected date."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR.parent))
sys.path.insert(0, str(_APP_DIR))

import config
from common import (
    inject_css,
    load_price_history,
    load_published_weights,
    load_reference_data,
    render_missing_data_alert,
    render_top_header,
    render_warning_alert,
)
from nifty_calc import engine, reference_data, validation

st.set_page_config(page_title="Constituent Table", layout="wide")
inject_css()
render_top_header()
st.title("Constituent Table")

constituents_df, divisor_df = load_reference_data()
readiness = validation.check_readiness(constituents_df, divisor_df)
if readiness.is_missing:
    render_missing_data_alert(readiness.as_banner_text())
    st.stop()

tickers = reference_data.all_tickers(constituents_df)

as_of_date = st.date_input("As of date", value=pd.Timestamp.today().normalize())
as_of_ts = pd.Timestamp(as_of_date)

readiness_for_date = validation.check_readiness(constituents_df, divisor_df, as_of_ts)
if readiness_for_date.is_missing:
    render_warning_alert(readiness_for_date.as_banner_text())
    st.stop()

price_dict, interval_used = load_price_history(
    tuple(tickers), as_of_ts - pd.Timedelta(days=10), as_of_ts, "1d"
)
close_panel = engine.build_close_panel(
    {t: df for t, df in price_dict.items() if t != config.OFFICIAL_INDEX_TICKER}
)

if close_panel.empty:
    st.warning("No price data available up to this date.")
    st.stop()

published_weights = load_published_weights()
snapshot = engine.snapshot_at(as_of_ts, constituents_df, divisor_df, close_panel, published_weights)

if snapshot.empty:
    st.warning("Could not compute a snapshot for this date - check price/reference data coverage.")
    st.stop()

actual_date = snapshot["as_of_date"].iloc[0]
if pd.Timestamp(actual_date).normalize() != as_of_ts.normalize():
    st.info(f"No trading data for {as_of_ts.date()} - showing the most recent prior session: {pd.Timestamp(actual_date).date()}.")

total_ffmc = snapshot["free_float_market_cap"].sum()
st.caption(f"{len(snapshot)} constituents | Total free-float market cap: {total_ffmc:,.0f}")

display_cols = {
    "ticker": "Ticker",
    "price": "Price",
    "shares_outstanding": "Shares Outstanding",
    "iwf": "IWF",
    "free_float_market_cap": "Free-Float Market Cap",
    "calculated_weight_pct": "Calculated Weight %",
    "price_change_pct": "Price Change %",
    "point_contribution": "NIFTY Point Contribution",
}
has_published = "published_weight_pct" in snapshot.columns and snapshot["published_weight_pct"].notna().any()
if has_published:
    display_cols["published_weight_pct"] = "Published Weight % (reference)"

table = snapshot[list(display_cols.keys())].rename(columns=display_cols)

number_formats = {
    "Price": "{:,.2f}",
    "Shares Outstanding": "{:,.0f}",
    "IWF": "{:.4f}",
    "Free-Float Market Cap": "{:,.0f}",
    "Calculated Weight %": "{:.3f}",
    "Price Change %": "{:+.2f}",
    "NIFTY Point Contribution": "{:+.3f}",
}
if has_published:
    number_formats["Published Weight % (reference)"] = "{:.3f}"
else:
    table["Published Weight % (reference)"] = "N/A (no source loaded)"

st.dataframe(
    table.style.format(number_formats, na_rep="N/A"),
    width="stretch",
    height=700,
)
