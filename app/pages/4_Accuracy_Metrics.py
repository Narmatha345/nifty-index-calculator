"""Accuracy Metrics: how closely the independently calculated NIFTY tracks
the official ^NSEI over a selected history. Calculated values are never
force-fit to match official - this page just measures the gap."""

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

st.set_page_config(page_title="Accuracy Metrics", layout="wide")
inject_css()
render_top_header()
st.title("Accuracy Metrics")

constituents_df, divisor_df = load_reference_data()
readiness = validation.check_readiness(constituents_df, divisor_df)
if readiness.is_missing:
    render_missing_data_alert(readiness.as_banner_text())
    st.stop()

tickers = reference_data.all_tickers(constituents_df)

today = pd.Timestamp.today().normalize()
start_date, end_date = st.date_input(
    "Date range", value=(today - pd.Timedelta(days=365), today), key="accuracy_range"
)
start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)

price_dict, interval_used = load_price_history(tuple(tickers), start_ts, end_ts, "1d")
official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
close_panel = engine.build_close_panel(
    {t: df for t, df in price_dict.items() if t != config.OFFICIAL_INDEX_TICKER}
)

if close_panel.empty or official_df.empty:
    st.warning("Not enough price data (calculated and/or official) in this range.")
    st.stop()

series = engine.reconstruct_series(
    close_panel.index, close_panel, constituents_df, divisor_df, official_series=official_df["Close"]
)
series = series.dropna(subset=["calculated", "official"])

if series.empty:
    st.warning("No overlapping calculated/official values in this range.")
    st.stop()

metrics = engine.accuracy_metrics(series["calculated"], series["official"])

m1, m2, m3, m4 = st.columns(4)
m1.metric("Current error", f"{metrics['current_error']:+.2f}")
m2.metric("Mean absolute error", f"{metrics['mean_absolute_error']:.2f}")
m3.metric("RMSE", f"{metrics['rmse']:.2f}")
m4.metric("Max error", f"{metrics['max_error']:.2f}")
st.caption(f"Based on {metrics['n_observations']} overlapping observations.")

series["error"] = series["calculated"] - series["official"]
fig = go.Figure(go.Scatter(x=series["date"], y=series["error"], mode="lines", name="Calculated - Official"))
fig.add_hline(y=0, line_dash="dot")
fig.update_layout(height=450, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Error (points)")
st.plotly_chart(fig, width="stretch")
