"""Discrepancy History: the full Calculated vs Actual vs ETF table (with
per-date coverage %) for the exact inputs set on Home, plus CSV export - the
one thing this page adds beyond Home's own chart/summary. Same calculation
model as Home.py (see engine.py) - a single baseline calibration, no daily
re-fitting. Uses Home's Weight Period / Analysis Period / ETF / Baseline
inputs directly (see common.read_home_inputs) rather than asking for them
again, so there's one place in the app to set them."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR.parent))
sys.path.insert(0, str(_APP_DIR))

import config
from common import (
    inject_css,
    load_price_history,
    read_home_inputs,
    render_home_inputs_recap,
    render_missing_data_alert,
    render_top_header,
    render_warning_alert,
)
from nifty_calc import engine, weights

st.set_page_config(page_title="Discrepancy History", layout="wide")
inject_css()
render_top_header()
st.title("Discrepancy History", anchor=False)

inputs = read_home_inputs()
if inputs is None:
    render_missing_data_alert("Set your Weight Period, Analysis Period, ETF, and Baseline on the Home page first.")
    st.page_link("Home.py", label="Go to Home", icon=":material/home:")
    st.stop()

render_home_inputs_recap(inputs)

selected_period = inputs["selected_period"]
start_ts, end_ts = inputs["start_ts"], inputs["end_ts"]
etf_ticker = inputs["etf_ticker"]
baseline_date = inputs["baseline_date"]

period_df = weights.get_weight_period(selected_period)
if period_df.empty:
    render_missing_data_alert(f"Official weight data is not available for {weights.format_period_label(selected_period)}.")
    st.stop()

weight_series = period_df.set_index("ticker")["weight_pct"]
tickers = list(weight_series.index)
fetch_tickers = tuple(sorted(set(tickers) | {config.OFFICIAL_INDEX_TICKER, etf_ticker}))
price_dict, interval_used = load_price_history(fetch_tickers, start_ts, end_ts, "1d")
st.caption(f"Resolution used: **{interval_used}**")

official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
etf_df = price_dict.get(etf_ticker, pd.DataFrame())
stock_prices = {t: df for t, df in price_dict.items() if t not in (config.OFFICIAL_INDEX_TICKER, etf_ticker)}
close_panel = engine.build_close_panel(stock_prices)

if close_panel.empty or official_df.empty:
    render_warning_alert("No price data available for this range.")
    st.stop()

official_series = official_df["Close"]
etf_series = etf_df["Close"] if not etf_df.empty else pd.Series(dtype=float)

weight_panel = engine.build_static_weight_panel(weight_series, close_panel.index)
raw_series, coverage_pct = engine.compute_raw_weighted_series(close_panel, weight_panel)

try:
    baseline_info = engine.calibrate_baseline(raw_series, official_series, baseline_date)
except ValueError as exc:
    render_missing_data_alert(str(exc))
    st.stop()

calculated_series = engine.compute_calculated_series(raw_series, baseline_info["normalization_factor"])

combined = pd.DataFrame(
    {"Calculated": calculated_series, "Actual": official_series, "ETF": etf_series, "Coverage %": coverage_pct}
).sort_index()
combined["Difference"] = combined["Calculated"] - combined["Actual"]
combined["Difference %"] = combined["Difference"] / combined["Actual"] * 100

with st.container(border=True):
    st.subheader("Calculated vs Actual vs ETF", anchor=False, icon=":material/show_chart:")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=combined.index, y=combined["Calculated"], name="Calculated NIFTY", mode="lines"))
    fig.add_trace(go.Scatter(x=combined.index, y=combined["Actual"], name="Actual NIFTY", mode="lines"))
    fig.add_trace(go.Scatter(x=combined.index, y=combined["ETF"], name="NIFTY ETF", mode="lines", yaxis="y2"))
    fig.update_layout(
        hovermode="x unified",
        height=460,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis=dict(title="Index value"),
        yaxis2=dict(title="ETF price", overlaying="y", side="right", showgrid=False),
    )
    st.plotly_chart(fig, width="stretch")

with st.container(border=True):
    st.subheader("Full data table", anchor=False, icon=":material/table_view:")
    display = combined.reset_index().rename(columns={"index": "Date"})
    st.dataframe(display, width="stretch", height=400)

    st.download_button(
        "Download as CSV",
        display.to_csv(index=False).encode("utf-8"),
        file_name=f"nifty_discrepancy_{start_ts.date()}_{end_ts.date()}.csv",
        mime="text/csv",
    )
