"""NIFTY 50 Index Calculator - live dashboard.

Shows Official NIFTY (^NSEI), independently Calculated NIFTY, and the
difference between them, plus a comparison chart. If reference data
(shares/IWF/membership/divisor) hasn't been supplied yet, shows a MISSING
DATA banner instead of computing with placeholders.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import (
    default_interval_for_range,
    inject_css,
    load_price_history,
    load_reference_data,
    render_hero,
    render_info_alert,
    render_missing_data_alert,
    render_top_header,
    resolve_range,
)
from nifty_calc import engine, reference_data, validation

st.set_page_config(page_title=f"{config.INDEX_NAME} Calculator", layout="wide")


def main():
    inject_css()
    render_top_header()
    render_hero("Independently reconstructed from free-float market cap - not derived from published index weights.")

    constituents_df, divisor_df = load_reference_data()
    readiness = validation.check_readiness(constituents_df, divisor_df)

    if readiness.is_missing:
        render_missing_data_alert(readiness.as_banner_text())
        render_info_alert(
            "Add real constituent and divisor data via the **Reference Data Manager** page "
            "(left sidebar) before the calculator can produce any numbers. "
            "No placeholder or invented values will be shown."
        )
        st.stop()

    tickers = reference_data.all_tickers(constituents_df)

    with st.sidebar:
        st.subheader("Chart range")
        range_choice = st.radio("Range", config.CHART_RANGE_OPTIONS, index=2, horizontal=False)
        if range_choice == "Custom":
            today = pd.Timestamp.today().normalize()
            custom_start, custom_end = st.date_input(
                "Custom range", value=(today - pd.Timedelta(days=30), today)
            )
            start_date, end_date = resolve_range(range_choice, custom_start, custom_end)
        else:
            start_date, end_date = resolve_range(range_choice)
        requested_interval = default_interval_for_range(range_choice)

    price_dict, interval_used = load_price_history(tuple(tickers), start_date, end_date, requested_interval)
    if interval_used != requested_interval:
        st.warning(
            f"Requested {requested_interval} resolution isn't available for this range - "
            f"showing **{interval_used}** resolution instead."
        )

    official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
    close_panel = engine.build_close_panel(
        {t: df for t, df in price_dict.items() if t != config.OFFICIAL_INDEX_TICKER}
    )

    if close_panel.empty or official_df.empty:
        st.warning("No price data available for the selected range yet. Try a different range.")
        st.stop()

    official_series = official_df["Close"]
    series = engine.reconstruct_series(
        close_panel.index, close_panel, constituents_df, divisor_df, official_series=official_series
    )
    series = series.dropna(subset=["calculated"])

    if series.empty:
        st.warning(
            "No calculated values could be produced for this range - check that reference data "
            "(shares/IWF/membership/divisor) covers these dates."
        )
        st.stop()

    latest = series.iloc[-1]
    official_latest = latest.get("official")
    calculated_latest = latest["calculated"]

    col1, col2, col3 = st.columns(3)
    col1.metric(
        f"Official {config.INDEX_NAME} ({config.OFFICIAL_INDEX_TICKER})",
        f"{official_latest:,.2f}" if pd.notna(official_latest) else "N/A",
    )
    col2.metric("Calculated NIFTY", f"{calculated_latest:,.2f}")
    if pd.notna(official_latest) and official_latest != 0:
        diff = calculated_latest - official_latest
        diff_pct = diff / official_latest * 100
        col3.metric("Difference", f"{diff:+,.2f}", f"{diff_pct:+.4f}%")
    else:
        col3.metric("Difference", "N/A")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series["date"], y=series["calculated"], name="Calculated NIFTY", mode="lines"))
    if "official" in series.columns:
        fig.add_trace(go.Scatter(x=series["date"], y=series["official"], name="Official NIFTY", mode="lines"))
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=30, b=10),
        height=500,
    )
    st.plotly_chart(fig, width="stretch")

    if "official" in series.columns:
        metrics = engine.accuracy_metrics(series["calculated"], series["official"])
        if metrics["n_observations"] > 0:
            st.subheader("Reconstruction accuracy (this range)")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current error", f"{metrics['current_error']:+.2f}")
            m2.metric("Mean absolute error", f"{metrics['mean_absolute_error']:.2f}")
            m3.metric("RMSE", f"{metrics['rmse']:.2f}")
            m4.metric("Max error", f"{metrics['max_error']:.2f}")


if __name__ == "__main__":
    main()
