"""Reference Data Manager: import/validate/replace the constituent, divisor,
and (optional) published-weight reference data, and run one-time divisor
calibration. This is the only place the app writes to data/reference/ - it
never invents values, only validates and stores what the user supplies."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR.parent))
sys.path.insert(0, str(_APP_DIR))

import config
from common import inject_css, load_price_history, load_reference_data, render_top_header
from nifty_calc import divisor as divisor_mod
from nifty_calc import engine, reference_data

st.set_page_config(page_title="Reference Data Manager", layout="wide")
inject_css()
render_top_header()
st.title("Reference Data Manager")
st.caption(
    "Upload real NSE reference data here. Nothing in this app fabricates shares outstanding, "
    "IWF, historical constituents, or divisor values - if a field is missing, it stays missing "
    "until you supply it."
)

constituents_df, divisor_df = load_reference_data()

# ---------------------------------------------------------------- Constituents
st.header("1. Constituents (shares outstanding, IWF, membership)")
st.write(f"Currently loaded: **{len(constituents_df)}** row(s) across **{len(reference_data.all_tickers(constituents_df))}** ticker(s).")

with open(config.CONSTITUENTS_TEMPLATE_PATH, "rb") as f:
    st.download_button("Download constituents template", f.read(), file_name="constituents_template.csv")

uploaded_constituents = st.file_uploader("Upload constituents CSV", type="csv", key="constituents_upload")
if uploaded_constituents is not None:
    try:
        new_df = reference_data.load_constituents(uploaded_constituents)
    except Exception as exc:
        st.error(f"Could not parse file: {exc}")
        new_df = None

    if new_df is not None:
        errors = reference_data.validate_constituents(new_df)
        if errors:
            st.error("Validation failed:")
            for e in errors:
                st.write(f"- {e}")
        elif reference_data.is_empty(new_df):
            st.warning("File parsed but contains no data rows (only the template header/comments).")
        else:
            st.success(f"Valid: {len(new_df)} row(s), {len(reference_data.all_tickers(new_df))} ticker(s).")
            st.dataframe(new_df, width="stretch", height=300)
            if st.button("Save as active constituent data"):
                reference_data.save_constituents(new_df)
                load_reference_data.clear()
                st.success("Saved. Reloading...")
                st.rerun()

st.divider()

# ---------------------------------------------------------------------- Divisor
st.header("2. Divisor history")
st.write(f"Currently loaded: **{len(divisor_df)}** period(s).")
if not divisor_mod.is_empty(divisor_df):
    st.dataframe(divisor_df, width="stretch", height=200)

with open(config.DIVISOR_HISTORY_TEMPLATE_PATH, "rb") as f:
    st.download_button("Download divisor history template", f.read(), file_name="divisor_history_template.csv")

uploaded_divisor = st.file_uploader("Upload divisor history CSV", type="csv", key="divisor_upload")
if uploaded_divisor is not None:
    try:
        new_divisor_df = divisor_mod.load_divisor_history(uploaded_divisor)
    except Exception as exc:
        st.error(f"Could not parse file: {exc}")
        new_divisor_df = None

    if new_divisor_df is not None:
        errors = divisor_mod.validate_divisor_history(new_divisor_df)
        if errors:
            st.error("Validation failed:")
            for e in errors:
                st.write(f"- {e}")
        elif divisor_mod.is_empty(new_divisor_df):
            st.warning("File parsed but contains no data rows.")
        else:
            st.success(f"Valid: {len(new_divisor_df)} period(s).")
            st.dataframe(new_divisor_df, width="stretch", height=200)
            if st.button("Save as active divisor history"):
                divisor_mod.save_divisor_history(new_divisor_df)
                load_reference_data.clear()
                st.success("Saved. Reloading...")
                st.rerun()

st.subheader("Calibrate a new divisor")
st.caption(
    "Do this once, at a timestamp where the official index and all constituent prices are "
    "available for approximately the same moment. Do not repeat this routinely - the "
    "calculated index should run independently after calibration."
)
if reference_data.is_empty(constituents_df):
    st.info("Load constituent data first.")
else:
    calib_date = st.date_input("Calibration date", value=pd.Timestamp.today().normalize(), key="calib_date")
    calib_reason = st.text_input("Reason", value="initial calibration")
    if st.button("Compute divisor for this date"):
        calib_ts = pd.Timestamp(calib_date)
        tickers = reference_data.all_tickers(constituents_df)
        price_dict, interval_used = load_price_history(tuple(tickers), calib_ts - pd.Timedelta(days=10), calib_ts, "1d")
        official_df = price_dict.get(config.OFFICIAL_INDEX_TICKER, pd.DataFrame())
        close_panel = engine.build_close_panel(
            {t: df for t, df in price_dict.items() if t != config.OFFICIAL_INDEX_TICKER}
        )
        official_series = official_df["Close"] if not official_df.empty else pd.Series(dtype=float)

        try:
            result = engine.calibrate_divisor_for_date(calib_ts, constituents_df, close_panel, official_series)
        except ValueError as exc:
            st.error(str(exc))
        else:
            use_date = result["use_date"]
            st.write(
                f"Date used: **{use_date.date()}** "
                f"({result['tickers_used']} of {result['tickers_total']} constituents had price data)"
            )
            st.write(f"Total free-float market cap: **{result['total_ffmc']:,.2f}**")
            st.write(f"Official {config.OFFICIAL_INDEX_TICKER} close: **{result['official_value']:,.2f}**")
            st.write(f"Computed divisor: **{result['divisor']:,.8f}**")

            st.session_state["pending_divisor"] = {
                "effective_from": use_date,
                "divisor": result["divisor"],
                "reason": calib_reason,
                "calibrated_at": str(pd.Timestamp.now()),
                "calibration_source": (
                    f"{config.OFFICIAL_INDEX_TICKER} close {use_date.date()} + "
                    f"{result['tickers_used']} constituent closes"
                ),
            }

    pending = st.session_state.get("pending_divisor")
    if pending:
        if st.button(f"Save divisor {pending['divisor']:.8f} effective {pending['effective_from'].date()}"):
            updated = divisor_mod.append_divisor_row(divisor_df, **pending)
            divisor_mod.save_divisor_history(updated)
            load_reference_data.clear()
            del st.session_state["pending_divisor"]
            st.success("Divisor saved. Reloading...")
            st.rerun()

st.divider()

# --------------------------------------------------------------- Published weights
st.header("3. Published weights (optional, for comparison only)")
published = reference_data.load_published_weights()
st.write(f"Currently loaded: **{len(published)}** ticker(s).")

with open(config.PUBLISHED_WEIGHTS_TEMPLATE_PATH, "rb") as f:
    st.download_button("Download published weights template", f.read(), file_name="published_weights_template.csv")

uploaded_weights = st.file_uploader("Upload published weights CSV", type="csv", key="weights_upload")
if uploaded_weights is not None:
    try:
        new_weights = reference_data.load_published_weights(uploaded_weights)
    except Exception as exc:
        st.error(f"Could not parse file: {exc}")
        new_weights = None

    if new_weights is not None:
        if new_weights.empty:
            st.warning("File parsed but contains no data rows.")
        else:
            st.success(f"Valid: {len(new_weights)} ticker(s).")
            st.dataframe(new_weights.rename("weight_pct"), width="stretch", height=250)
            if st.button("Save as active published weights"):
                uploaded_weights.seek(0)
                with open(config.PUBLISHED_WEIGHTS_PATH, "wb") as out:
                    out.write(uploaded_weights.read())
                st.success("Saved.")
                st.rerun()
