"""Historical Reconstruction: Calculated NIFTY vs Official NIFTY across any
date range, using the shares/IWF/membership/divisor applicable on each date."""

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

st.set_page_config(page_title="Historical Reconstruction", layout="wide")
inject_css()
render_top_header()
st.title("Historical Reconstruction")

constituents_df, divisor_df = load_reference_data()
readiness = validation.check_readiness(constituents_df, divisor_df)
if readiness.is_missing:
    render_missing_data_alert(readiness.as_banner_text())
    st.stop()

tickers = reference_data.all_tickers(constituents_df)

today = pd.Timestamp.today().normalize()
start_date, end_date = st.date_input(
    "Date range", value=(today - pd.Timedelta(days=180), today)
)
start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)

price_dict, interval_used = load_price_history(tuple(tickers), start_ts, end_ts, "1d")
st.caption(f"Resolution used: **{interval_used}**")

official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
close_panel = engine.build_close_panel(
    {t: df for t, df in price_dict.items() if t != config.OFFICIAL_INDEX_TICKER}
)

if close_panel.empty:
    st.warning("No price data available for this range.")
    st.stop()

official_series = official_df["Close"] if not official_df.empty else None
series = engine.reconstruct_series(
    close_panel.index, close_panel, constituents_df, divisor_df, official_series=official_series
)
series = series.dropna(subset=["calculated"])

if series.empty:
    st.warning("No calculated values for this range - reference data may not cover these dates.")
    st.stop()

fig = go.Figure()
fig.add_trace(go.Scatter(x=series["date"], y=series["calculated"], name="Calculated NIFTY", mode="lines"))
if "official" in series.columns:
    fig.add_trace(go.Scatter(x=series["date"], y=series["official"], name="Official NIFTY", mode="lines"))
fig.update_layout(hovermode="x unified", height=500, margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig, width="stretch")

display = series.rename(columns={"date": "Date", "calculated": "Calculated", "official": "Official"})
if "Official" in display.columns:
    display["Difference"] = display["Calculated"] - display["Official"]
st.dataframe(display, width="stretch", height=400)

st.download_button(
    "Download as CSV",
    display.to_csv(index=False).encode("utf-8"),
    file_name=f"nifty_reconstruction_{start_ts.date()}_{end_ts.date()}.csv",
    mime="text/csv",
)
