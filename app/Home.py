"""NIFTY discrepancy analysis dashboard - compares three time-series:

  1. Calculated NIFTY   - Sum(Price x official NSE weight), calibrated once
                          against ^NSEI at a chosen baseline date.
  2. Actual NIFTY 50    - ^NSEI, fetched live from Yahoo Finance.
  3. NIFTY ETF          - a configurable NIFTY-tracking ETF's market price.

This tool does not attempt to reconstruct the index independently and does
not label any series as "correct" - it exists to surface where/when the
three diverge. See README.md for the full calculation model.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import (
    inject_css,
    load_price_history,
    load_weights_history,
    render_hero,
    render_info_alert,
    render_missing_data_alert,
    render_pill,
    render_top_header,
    render_warning_alert,
    resample_series,
    resolve_range,
    set_home_inputs,
)
from nifty_calc import engine, weights

st.set_page_config(page_title=f"{config.INDEX_NAME} Discrepancy Analysis", layout="wide")


def main():
    inject_css()
    render_top_header()
    render_hero(
        "Compares the officially weighted NIFTY 50 against the live ^NSEI value and a NIFTY ETF, "
        "to surface where and when they diverge - not to declare one \"correct\"."
    )

    # ----------------------------------------------------- Analysis settings
    st.subheader("Analysis settings", anchor=False, icon=":material/tune:")
    settings_row1_col1, settings_row1_col2 = st.columns([1.4, 1])

    with settings_row1_col1:
        with st.container(border=True):
            st.subheader("Weight Period", anchor=False, help="The single official NSE monthly weight snapshot used for the whole analysis below.")
            available_periods = weights.list_available_periods()
            if available_periods:
                period_labels = {p: weights.format_period_label(p) for p in available_periods}
                selected_period = st.selectbox(
                    "Official NIFTY 50 weight set",
                    options=available_periods,
                    format_func=lambda p: period_labels[p],
                    index=0,
                    label_visibility="collapsed",
                    key="home_weight_period",
                )
            else:
                selected_period = None
                st.caption("No official weight data available yet - fetch or import one below.")

            wp_col1, wp_col2, wp_col3 = st.columns(3)
            with wp_col1, st.expander("Fetch a different month", icon=":material/cloud_download:"):
                pick_month = st.date_input("Month", value=pd.Timestamp.today().normalize().replace(day=1))
                if st.button("Check / fetch this month", width="stretch"):
                    fetched = weights.get_weight_period(pd.Timestamp(pick_month).replace(day=1), use_network=True)
                    if fetched.empty:
                        st.error(f"Official weight data is not available for {weights.format_period_label(pick_month)}.")
                    else:
                        st.success(f"Loaded {weights.format_period_label(pick_month)}. Select it above.")
                        load_weights_history.clear()
                        st.rerun()

            with wp_col2, st.expander("Check coverage across a range", icon=":material/fact_check:"):
                today_ts = pd.Timestamp.today().normalize()
                check_range = st.date_input(
                    "Check coverage for range", value=(today_ts - pd.Timedelta(days=365), today_ts), key="check_range"
                )
                if len(check_range) != 2:
                    st.caption("Pick both a start and end date.")
                else:
                    check_start_ts, check_end_ts = pd.Timestamp(check_range[0]), pd.Timestamp(check_range[1])

                    if st.button("Check (cache only)", width="stretch", key="cov_check_cache"):
                        cov_history, cov_missing = weights.get_history(check_start_ts, check_end_ts, use_network=False)
                        st.session_state["ref_check_result"] = (cov_history, cov_missing)
                    if st.button("Fetch/refresh from NSE", type="primary", width="stretch", key="cov_check_fetch"):
                        with st.spinner("Contacting NSE Indices..."):
                            cov_history, cov_missing = weights.get_history(check_start_ts, check_end_ts, use_network=True)
                        st.session_state["ref_check_result"] = (cov_history, cov_missing)
                        load_weights_history.clear()

                    cov_result = st.session_state.get("ref_check_result")
                    if cov_result is not None:
                        cov_history, cov_missing = cov_result
                        cov_months_total = len(weights.month_starts_between(check_start_ts, check_end_ts))
                        st.write(f"**{cov_months_total - len(cov_missing)}** of **{cov_months_total}** month(s) have weight data.")
                        if cov_missing:
                            st.warning(f"Missing months: {', '.join(cov_missing)}")

            with wp_col3, st.expander("Import verified CSV", icon=":material/upload_file:"):
                current_reference = weights.load_reference_weights()
                st.caption(
                    f"Currently imported: **{len(current_reference)}** row(s) covering "
                    f"**{current_reference['as_of_date'].nunique() if not current_reference.empty else 0}** month(s)."
                )
                with open(config.WEIGHTS_REFERENCE_TEMPLATE_PATH, "rb") as f:
                    st.download_button("Download template", f.read(), file_name="weights_history_template.csv", width="stretch")
                st.caption("Accepts either NSE's raw nifty50_mcwb.csv export or this app's own schema - both auto-detected.")
                uploaded = st.file_uploader("Upload verified weight-history CSV", type="csv", key="weights_upload")
                if uploaded is not None:
                    try:
                        new_df = weights.load_uploaded_weights_csv(uploaded)
                    except Exception as exc:
                        st.error(f"Could not parse file: {exc}")
                        new_df = None

                    if new_df is not None:
                        upload_errors = weights.validate_reference_weights(new_df)
                        if upload_errors:
                            st.error("Validation failed:")
                            for e in upload_errors:
                                st.write(f"- {e}")
                        elif weights.is_empty(new_df):
                            st.warning("File parsed but contains no data rows.")
                        else:
                            st.success(f"Valid: {len(new_df)} row(s).")
                            if st.button("Merge into active fallback data", type="primary", width="stretch"):
                                merged = pd.concat([current_reference, new_df], ignore_index=True)
                                merged = merged.drop_duplicates(subset=["as_of_date", "ticker"], keep="last")
                                merged = merged.sort_values(["as_of_date", "ticker"]).reset_index(drop=True)
                                weights.save_reference_weights(merged)
                                load_weights_history.clear()
                                st.success("Saved. Reloading...")
                                st.rerun()

    with settings_row1_col2:
        with st.container(border=True):
            st.subheader("Analysis period", anchor=False)
            range_choice = st.radio(
                "Range", config.CHART_RANGE_OPTIONS, index=2, horizontal=True,
                key="home_range_choice",
            )
            if range_choice == "Custom":
                today = pd.Timestamp.today().normalize()
                custom_range = st.date_input(
                    "Custom range", value=(today - pd.Timedelta(days=180), today),
                    key="home_custom_range",
                )
                if len(custom_range) != 2:
                    st.caption("Pick both a start and end date to continue.")
                    st.stop()
                start_ts, end_ts = resolve_range(range_choice, custom_range[0], custom_range[1])
            else:
                start_ts, end_ts = resolve_range(range_choice)

        settings_row2_col1, settings_row2_col2 = st.columns(2)
        with settings_row2_col1, st.container(border=True):
            st.subheader("NIFTY ETF", anchor=False)
            etf_ticker = st.selectbox(
                "ETF",
                options=list(config.ETF_TICKER_OPTIONS.keys()),
                format_func=lambda t: f"{t} - {config.ETF_TICKER_OPTIONS[t]}",
                index=list(config.ETF_TICKER_OPTIONS.keys()).index(config.DEFAULT_ETF_TICKER),
                label_visibility="collapsed",
                key="home_etf_ticker",
            )

        with settings_row2_col2, st.container(border=True):
            st.subheader("Baseline", anchor=False)
            use_custom_baseline = st.checkbox("Use a different baseline date", value=False, key="home_use_custom_baseline")
            baseline_date = (
                st.date_input("Baseline date", value=start_ts.date(), label_visibility="collapsed", key="home_baseline_date")
                if use_custom_baseline else start_ts.date()
            )

    with st.container(border=True):
        st.subheader("Display settings", anchor=False, icon=":material/display_settings:")
        disp_col1, disp_col2 = st.columns(2)
        with disp_col1:
            interval_choice = st.selectbox("Chart resolution", ["Daily", "Weekly", "Monthly"], index=0, key="home_interval_choice")
        with disp_col2:
            deviation_threshold = st.slider(
                "Flag dates where |diff| exceeds (%)", min_value=0.1, max_value=10.0,
                value=config.DEFAULT_DEVIATION_FLAG_PCT, step=0.1, key="home_deviation_threshold",
            )

    if selected_period is None:
        render_missing_data_alert(
            "No official NIFTY 50 weight period is available yet. Fetch or import one via the "
            "sidebar or the Reference Data Manager page before running the analysis."
        )
        st.stop()

    set_home_inputs(
        selected_period=selected_period,
        start_ts=start_ts,
        end_ts=end_ts,
        etf_ticker=etf_ticker,
        baseline_date=baseline_date,
        deviation_threshold=deviation_threshold,
    )

    st.markdown(
        f"{render_pill(f'Weight period &nbsp;<b>{weights.format_period_label(selected_period)}</b>')} "
        f"&nbsp;{render_pill(f'Analysis period &nbsp;<b>{start_ts.date()} &rarr; {end_ts.date()}</b>', neutral=True)}",
        unsafe_allow_html=True,
    )
    st.write("")

    # ----------------------------------------------------- Official weights
    period_df = weights.get_weight_period(selected_period)
    if period_df.empty:
        render_missing_data_alert(
            f"Official weight data is not available for {weights.format_period_label(selected_period)}."
        )
        st.stop()

    weight_series = period_df.set_index("ticker")["weight_pct"]
    tickers = list(weight_series.index)

    # --------------------------------------------------------------- Prices
    fetch_tickers = tuple(sorted(set(tickers) | {config.OFFICIAL_INDEX_TICKER, etf_ticker}))
    price_dict, interval_used = load_price_history(fetch_tickers, start_ts, end_ts, "1d")
    if interval_used != "1d":
        render_warning_alert(f"Daily resolution wasn't available for this range - showing **{interval_used}** instead.")

    official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
    etf_df = price_dict.get(etf_ticker, pd.DataFrame())
    stock_prices = {t: df for t, df in price_dict.items() if t not in (config.OFFICIAL_INDEX_TICKER, etf_ticker)}
    close_panel = engine.build_close_panel(stock_prices)

    if close_panel.empty or official_df.empty:
        render_warning_alert("No price data available for the selected range yet. Try a different range.")
        st.stop()

    official_series = official_df["Close"]
    etf_series = etf_df["Close"] if not etf_df.empty else pd.Series(dtype=float)

    # ------------------------------------------------------------ Calculate
    weight_panel = engine.build_static_weight_panel(weight_series, close_panel.index)
    raw_series, coverage_pct = engine.compute_raw_weighted_series(close_panel, weight_panel)

    try:
        baseline_info = engine.calibrate_baseline(raw_series, official_series, baseline_date)
    except ValueError as exc:
        render_missing_data_alert(str(exc))
        st.stop()

    calculated_series = engine.compute_calculated_series(raw_series, baseline_info["normalization_factor"])

    low_coverage_dates = coverage_pct[coverage_pct < 98.0].dropna()
    if not low_coverage_dates.empty:
        render_warning_alert(
            f"{len(low_coverage_dates)} date(s) had official-weight coverage below 98% (missing prices for "
            "some constituents that day) - the calculated value on those dates is based on partial coverage."
        )

    # ------------------------------------------------------------- Metrics
    metrics = engine.discrepancy_metrics(calculated_series, official_series)
    if metrics["n_observations"] == 0:
        render_warning_alert("No overlapping calculated/official values in this range.")
        st.stop()

    latest_calc = calculated_series.dropna().iloc[-1]
    latest_official = official_series.dropna().iloc[-1]
    latest_etf = etf_series.dropna().iloc[-1] if not etf_series.dropna().empty else None

    with st.container(border=True):
        st.subheader("Summary", anchor=False, icon=":material/dashboard:")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Calculated NIFTY", f"{latest_calc:,.2f}")
        c2.metric(f"Actual NIFTY ({config.OFFICIAL_INDEX_TICKER})", f"{latest_official:,.2f}")
        c3.metric(f"NIFTY ETF ({etf_ticker})", f"{latest_etf:,.2f}" if latest_etf is not None else "N/A")
        c4.metric("Current difference", f"{metrics['current_diff']:+,.2f}", f"{metrics['current_diff_pct']:+.3f}%")
        c5.metric("Max deviation", f"{metrics['max_abs_diff']:+,.2f}", f"{metrics['max_abs_diff_pct']:+.3f}%")

        render_info_alert(
            f"Baseline: <strong>{baseline_info['baseline_date_used'].date()}</strong> "
            f"(Calculated {baseline_info['raw_value']:,.2f} &rarr; normalized to Actual "
            f"{baseline_info['official_value']:,.2f}, factor = {baseline_info['normalization_factor']:.6f}). "
            "This factor is fixed from this one date and is not recalculated day-to-day."
        )

    # ----------------------------------------------------------------- Chart
    combined = pd.DataFrame(
        {"Calculated": calculated_series, "Actual": official_series, "ETF": etf_series}
    ).sort_index()
    diff = combined["Calculated"] - combined["Actual"]
    diff_pct = diff / combined["Actual"] * 100
    display = resample_series(combined, interval_choice)
    display_diff = diff.reindex(display.index)
    display_diff_pct = diff_pct.reindex(display.index)

    chart_card = st.container(border=True)
    chart_card.subheader("Calculated vs Actual vs ETF", anchor=False, icon=":material/show_chart:")

    _CALC_COLOR, _ACTUAL_COLOR, _ETF_COLOR = "#2563EB", "#93C5FD", "#EF4444"
    chart_card.markdown(
        "<div style='display:flex; gap:1.25rem; flex-wrap:wrap; margin-bottom:0.5rem;'>"
        + "".join(
            f"<span style='display:inline-flex;align-items:center;gap:.4rem;font-size:.85rem;color:#334155;'>"
            f"<span style='width:11px;height:11px;border-radius:50%;background:{color};display:inline-block;'></span>{label}</span>"
            for label, color in [
                ("Calculated NIFTY", _CALC_COLOR),
                ("Actual NIFTY", _ACTUAL_COLOR),
                ("NIFTY ETF", _ETF_COLOR),
            ]
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # A custom HTML legend above (rather than Plotly's built-in one) avoids it
    # ever overlapping or losing entries to the rangeselector/rangeslider on
    # narrow (mobile) widths - it's plain flow layout, not Plotly's own
    # positioning math, so it's correct at every screen size by construction.
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=display.index, y=display["Calculated"], name="Calculated", mode="lines",
            line=dict(color=_CALC_COLOR),
            customdata=pd.concat([display_diff, display_diff_pct], axis=1).values,
            hovertemplate="<b>Calculated NIFTY</b>: %{y:,.2f}<br>Diff vs Actual: %{customdata[0]:+,.2f} (%{customdata[1]:+.3f}%)<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=display.index, y=display["Actual"], name="Actual", mode="lines",
            line=dict(color=_ACTUAL_COLOR),
            hovertemplate="<b>Actual NIFTY</b>: %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=display.index, y=display["ETF"], name="ETF", mode="lines", yaxis="y2",
            line=dict(color=_ETF_COLOR),
            hovertemplate="<b>NIFTY ETF</b>: %{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=10),
        height=560,
        yaxis=dict(title="Index value"),
        yaxis2=dict(title="ETF price", overlaying="y", side="right", showgrid=False),
        xaxis=dict(
            type="date",
            rangeslider=dict(visible=True),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="MAX"),
                ]
            ),
        ),
    )
    chart_card.plotly_chart(fig, width="stretch")

    # ------------------------------------------------------- Discrepancy
    with st.container(border=True):
        st.subheader("Discrepancy analysis", anchor=False, icon=":material/insights:")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Mean absolute diff", f"{metrics['mean_abs_diff']:,.2f}", f"{metrics['mean_abs_diff_pct']:.3f}% avg")
        m2.metric("RMSE", f"{metrics['rmse']:,.2f}")
        m3.metric("Max deviation date", str(metrics["max_abs_diff_date"].date()))
        m4.metric("Observations", f"{metrics['n_observations']:,}")

        flagged = engine.flag_large_deviations(calculated_series, official_series, deviation_threshold)
        st.caption(f"Dates where |Calculated - Actual| / Actual exceeds {deviation_threshold:.1f}%: **{len(flagged)}**")
        if not flagged.empty:
            table = flagged.rename(
                columns={
                    "date": "Date", "calculated": "Calculated", "official": "Actual",
                    "diff": "Difference", "diff_pct": "Difference %",
                }
            )
            st.dataframe(
                table.style.format(
                    {"Calculated": "{:,.2f}", "Actual": "{:,.2f}", "Difference": "{:+,.2f}", "Difference %": "{:+.3f}"}
                ),
                width="stretch", height=min(400, 60 + 35 * len(table)),
            )

    # ----------------------------------------------------- Constituent table
    with st.container(border=True):
        header_col, pill_col = st.columns([4, 1])
        header_col.subheader("Constituent weights", anchor=False, icon=":material/table_chart:")
        pill_col.markdown(
            f"<div style='text-align:right; padding-top:0.6rem;'>{render_pill(weights.format_period_label(selected_period))}</div>",
            unsafe_allow_html=True,
        )
        snapshot = period_df.set_index("ticker")[["company_name", "industry", "weight_pct", "as_of_date"]]
        if not snapshot.empty:
            latest_prices = close_panel.iloc[-1] if not close_panel.empty else pd.Series(dtype=float)
            snap_display = snapshot.copy()
            snap_display["price"] = latest_prices.reindex(snap_display.index)
            snap_display = snap_display.reset_index().rename(
                columns={
                    "ticker": "Ticker", "company_name": "Company", "industry": "Industry",
                    "weight_pct": "Official Weight %", "price": "Price", "as_of_date": "Weight As Of",
                }
            ).sort_values("Official Weight %", ascending=False)
            st.dataframe(
                snap_display.style.format(
                    {"Official Weight %": "{:.2f}", "Price": "{:,.2f}"}, na_rep="N/A"
                ),
                width="stretch", height=450,
            )

        # --------------------------------------------------------- Data status
        with st.expander("Data source / status", icon=":material/info:"):
            st.write(
                f"- Weight period: **{weights.format_period_label(selected_period)}** "
                f"(official as of {pd.Timestamp(period_df['as_of_date'].iloc[0]).date()}), held constant "
                "across the whole analysis period."
            )
            st.write(f"- Constituent universe: **{len(tickers)}** ticker(s).")
            st.write(f"- Price resolution used: **{interval_used}**.")
            st.write(f"- ETF: **{etf_ticker}** ({config.ETF_TICKER_OPTIONS[etf_ticker]}).")
            st.write(
                f"- Baseline date used: **{baseline_info['baseline_date_used'].date()}** "
                f"(requested {baseline_info['baseline_date_requested'].date()})."
            )


if __name__ == "__main__":
    main()
