"""Accuracy Metrics: how closely Calculated NIFTY tracks Actual NIFTY over
Home's chosen Analysis Period, and where the largest deviations occur -
plus the Calculated-minus-Actual trend line, which Home's dashboard doesn't
show. Calculated values are never force-fit to match Actual - this page
only measures the gap. Uses Home's Weight Period / Analysis Period /
Baseline / Deviation-flag inputs directly (see common.read_home_inputs)
rather than asking for them again."""

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
    price_fetch_window,
    read_home_inputs,
    render_home_inputs_recap,
    render_missing_data_alert,
    render_top_header,
    render_warning_alert,
)
from nifty_calc import corporate_actions, engine, weights

st.set_page_config(page_title="Accuracy Metrics", layout="wide")
inject_css()
render_top_header()
st.title("Accuracy Metrics", anchor=False)

inputs = read_home_inputs()
if inputs is None:
    render_missing_data_alert("Set your Weight Period, Analysis Period, and Baseline on the Home page first.")
    st.page_link("Home.py", label="Go to Home", icon=":material/home:")
    st.stop()

render_home_inputs_recap(inputs)

selected_period = inputs["selected_period"]
start_ts, end_ts = inputs["start_ts"], inputs["end_ts"]
baseline_date = inputs["baseline_date"]
deviation_threshold = inputs["deviation_threshold"]

period_df = weights.get_weight_period(selected_period)
if period_df.empty:
    render_missing_data_alert(f"Official weight data is not available for {weights.format_period_label(selected_period)}.")
    st.stop()

weight_series = period_df.set_index("ticker")["weight_pct"]
weight_as_of = period_df["as_of_date"].max()
tickers = list(weight_series.index)
fetch_tickers = tuple(sorted(set(corporate_actions.price_sources(tickers)) | {config.OFFICIAL_INDEX_TICKER}))
fetch_start, fetch_end = price_fetch_window(start_ts, end_ts, weight_as_of)
price_dict, interval_used = load_price_history(fetch_tickers, fetch_start, fetch_end, "1d")
official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
full_close_panel = corporate_actions.build_constituent_close_panel(tickers, price_dict, weight_as_of)
anchor = engine.anchor_prices(full_close_panel, weight_as_of) if not full_close_panel.empty else pd.Series(dtype=float)
close_panel = full_close_panel.loc[start_ts:end_ts]

if close_panel.empty or official_df.empty:
    render_warning_alert("Not enough price data (calculated and/or actual) in this range.")
    st.stop()

official_series = official_df["Close"].loc[start_ts:end_ts]
weight_panel = engine.build_static_weight_panel(weight_series, close_panel.index)
raw_series, coverage_pct = engine.compute_raw_weighted_series(close_panel, weight_panel, anchor)

try:
    baseline_info = engine.calibrate_baseline(raw_series, official_series, baseline_date)
except ValueError as exc:
    render_missing_data_alert(str(exc))
    st.stop()

calculated_series = engine.compute_calculated_series(raw_series, baseline_info["normalization_factor"])
metrics = engine.discrepancy_metrics(calculated_series, official_series)

if metrics["n_observations"] == 0:
    render_warning_alert("No overlapping calculated/actual values in this range.")
    st.stop()

with st.container(border=True):
    st.subheader("Accuracy", anchor=False, icon=":material/insights:")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current diff", f"{metrics['current_diff']:+,.2f}", f"{metrics['current_diff_pct']:+.3f}%")
    m2.metric("Mean absolute diff", f"{metrics['mean_abs_diff']:,.2f}", f"{metrics['mean_abs_diff_pct']:.3f}% avg")
    m3.metric("RMSE", f"{metrics['rmse']:,.2f}")
    m4.metric("Max deviation", f"{metrics['max_diff']:+,.2f}", f"{metrics['max_abs_diff_pct']:+.3f}%")
    st.caption(f"Based on {metrics['n_observations']} overlapping observations. Max deviation on **{metrics['max_abs_diff_date'].date()}**.")

with st.container(border=True):
    st.subheader("Difference over time", anchor=False, icon=":material/show_chart:")
    aligned = pd.DataFrame({"calculated": calculated_series, "official": official_series}).dropna()
    aligned["diff"] = aligned["calculated"] - aligned["official"]
    fig = go.Figure(go.Scatter(x=aligned.index, y=aligned["diff"], mode="lines", name="Calculated - Actual"))
    fig.add_hline(y=0, line_dash="dot")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Difference (points)")
    st.plotly_chart(fig, width="stretch")

with st.container(border=True):
    st.subheader("Unusually large deviations", anchor=False, icon=":material/rule:")
    flagged = engine.flag_large_deviations(calculated_series, official_series, deviation_threshold)
    st.caption(f"Dates where |diff| / Actual exceeds {deviation_threshold:.1f}% (set on Home): **{len(flagged)}**")
    if not flagged.empty:
        table = flagged.rename(
            columns={"date": "Date", "calculated": "Calculated", "official": "Actual", "diff": "Difference", "diff_pct": "Difference %"}
        )
        st.dataframe(
            table.style.format({"Calculated": "{:,.2f}", "Actual": "{:,.2f}", "Difference": "{:+,.2f}", "Difference %": "{:+.3f}"}),
            width="stretch", height=min(450, 60 + 35 * len(table)),
        )
