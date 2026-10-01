"""Constituent Weights: the official NSE weight of each NIFTY 50 stock as of
a chosen date, plus how any selected stock's official weight has moved over
time. Weights come directly from NSE Indices - never calculated/invented."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR.parent))
sys.path.insert(0, str(_APP_DIR))

import config
from common import inject_css, load_price_history, load_weights_history, render_missing_data_alert, render_top_header, render_warning_alert
from nifty_calc import corporate_actions, validation, weights

st.set_page_config(page_title="Constituent Weights", layout="wide")
inject_css()
render_top_header()
st.title("Constituent Weights")

as_of_date = st.date_input("As of date", value=pd.Timestamp.today().normalize())
as_of_ts = pd.Timestamp(as_of_date)

history_start = as_of_ts - pd.Timedelta(days=365 * 2)
weights_history, missing_months = load_weights_history(history_start, as_of_ts)

readiness = validation.check_readiness(weights_history, missing_months, as_of_ts)
if weights.is_empty(weights_history):
    render_missing_data_alert(readiness.as_banner_text())
    st.stop()

snapshot = weights.get_weight_snapshot(weights_history, as_of_ts)
if snapshot.empty:
    render_missing_data_alert(f"No official weight snapshot on or before {as_of_ts.date()}.")
    st.stop()

actual_snapshot_date = pd.Timestamp(snapshot["as_of_date"].iloc[0])
if actual_snapshot_date.normalize() != as_of_ts.normalize():
    st.info(
        f"NSE publishes this monthly - showing the most recent snapshot on/before {as_of_ts.date()}: "
        f"**{actual_snapshot_date.date()}**."
    )

tickers = list(snapshot.index)
price_dict, _ = load_price_history(
    tuple(corporate_actions.price_sources(tickers)), actual_snapshot_date - pd.Timedelta(days=10), actual_snapshot_date, "1d"
)
close_panel = corporate_actions.build_constituent_close_panel(tickers, price_dict, actual_snapshot_date)
latest_price = close_panel.iloc[-1] if not close_panel.empty else pd.Series(dtype=float)

table = snapshot.copy()
table["price"] = latest_price.reindex(table.index)
table = table.reset_index().rename(
    columns={
        "ticker": "Ticker", "company_name": "Company", "industry": "Industry",
        "weight_pct": "Official Weight %", "price": "Price", "as_of_date": "Weight As Of",
    }
).sort_values("Official Weight %", ascending=False)

st.caption(f"{len(table)} constituents as of **{actual_snapshot_date.date()}** (official NSE weight snapshot).")
st.dataframe(
    table.style.format({"Official Weight %": "{:.2f}", "Price": "{:,.2f}"}, na_rep="N/A"),
    width="stretch", height=650,
)

st.divider()
st.subheader("Weight history for a stock")
selected = st.multiselect("Tickers", options=sorted(weights_history["ticker"].unique()), default=tickers[:3])
if selected:
    hist = weights_history[weights_history["ticker"].isin(selected)]
    fig = go.Figure()
    for t in selected:
        series = hist[hist["ticker"] == t].sort_values("as_of_date")
        fig.add_trace(go.Scatter(x=series["as_of_date"], y=series["weight_pct"], name=t, mode="lines+markers"))
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Official weight (%)")
    st.plotly_chart(fig, width="stretch")
