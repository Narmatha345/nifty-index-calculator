"""Contribution Analysis: which stocks drove the calculated NIFTY's move
over a selected date range. Contributions reconcile exactly to the total
calculated change (see nifty_calc.engine.contribution_analysis)."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR.parent))
sys.path.insert(0, str(_APP_DIR))

import config
from common import inject_css, load_price_history, load_reference_data, render_missing_data_alert, render_top_header
from nifty_calc import engine, reference_data, validation

st.set_page_config(page_title="Contribution Analysis", layout="wide")
inject_css()
render_top_header()
st.title("Contribution Analysis")

constituents_df, divisor_df = load_reference_data()
readiness = validation.check_readiness(constituents_df, divisor_df)
if readiness.is_missing:
    render_missing_data_alert(readiness.as_banner_text())
    st.stop()

tickers = reference_data.all_tickers(constituents_df)

today = pd.Timestamp.today().normalize()
start_date, end_date = st.date_input(
    "Date range", value=(today - pd.Timedelta(days=7), today), key="contrib_range"
)
start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)

price_dict, interval_used = load_price_history(tuple(tickers), start_ts, end_ts, "1d")
close_panel = engine.build_close_panel(
    {t: df for t, df in price_dict.items() if t != config.OFFICIAL_INDEX_TICKER}
)

if close_panel.empty or len(close_panel.index) < 2:
    st.warning("Not enough price data in this range to compute contributions.")
    st.stop()

range_start = close_panel.index.min()
range_end = close_panel.index.max()

contrib = engine.contribution_analysis(range_start, range_end, close_panel, constituents_df, divisor_df)
series = engine.reconstruct_series([range_start, range_end], close_panel, constituents_df, divisor_df)
series = series.dropna(subset=["calculated"])

if contrib.empty or len(series) < 2:
    st.warning("Could not compute contributions for this range - check reference data coverage.")
    st.stop()

index_change = series["calculated"].iloc[-1] - series["calculated"].iloc[0]
contrib_sum = contrib["point_contribution"].sum()

st.caption(
    f"{range_start.date()} → {range_end.date()} | "
    f"Calculated NIFTY change: {index_change:+.2f} pts | "
    f"Sum of contributions: {contrib_sum:+.2f} pts"
)
if abs(index_change - contrib_sum) > 1e-6:
    st.warning("Contributions do not fully reconcile to the index change - this indicates a data gap.")

fig = go.Figure(go.Bar(x=contrib["ticker"], y=contrib["point_contribution"]))
fig.update_layout(height=450, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="NIFTY points")
st.plotly_chart(fig, width="stretch")

display = contrib.rename(columns={"ticker": "Ticker", "point_contribution": "Point Contribution"})
st.dataframe(
    display.style.format({"Point Contribution": "{:+.3f}"}),
    width="stretch",
    height=500,
)
