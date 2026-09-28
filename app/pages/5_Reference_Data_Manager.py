"""Reference Data Manager: read-only status view of the official NIFTY 50
weight data - which months are available locally, and what's been manually
imported as a fallback. All the actual fetch/check/import controls live on
the Home page (Weight Period card) so every input field in the app has one
home. This page never writes anything - it only reports what's already on
disk (see nifty_calc/weights.py)."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_APP_DIR.parent))
sys.path.insert(0, str(_APP_DIR))

from common import inject_css, render_pill, render_top_header
from nifty_calc import weights

st.set_page_config(page_title="Reference Data Manager", layout="wide")
inject_css()
render_top_header()
st.title("Reference Data Manager", anchor=False)
st.caption(
    "Official NIFTY 50 weights are fetched automatically from NSE Indices (niftyindices.com) and cached "
    "locally. This page only reports status - fetch a month, check coverage, or import a verified CSV "
    "from the **Weight Period** card on the Home page sidebar."
)

available_periods = weights.list_available_periods()
current_reference = weights.load_reference_weights()
st.markdown(
    f"{render_pill(f'{len(available_periods)} Weight Period(s) available')} "
    f"&nbsp;{render_pill(f'{len(current_reference)} manually imported row(s)', neutral=True)}",
    unsafe_allow_html=True,
)
st.write("")

with st.container(border=True):
    st.subheader("Available Weight Periods", anchor=False, icon=":material/inventory_2:")
    if not available_periods:
        st.info("No official weight data available yet. Go to Home &rarr; Weight Period card to fetch or import one.")
    else:
        rows = []
        for period in available_periods:
            period_df = weights.get_weight_period(period, use_network=False)
            rows.append(
                {
                    "Weight Period": weights.format_period_label(period),
                    "Official As Of": pd.Timestamp(period_df["as_of_date"].iloc[0]).date() if not period_df.empty else None,
                    "Constituents": len(period_df),
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", height=min(450, 60 + 35 * len(rows)))

with st.container(border=True):
    st.subheader("Manually imported fallback data", anchor=False, icon=":material/upload_file:")
    if current_reference.empty:
        st.caption("Nothing imported yet - use the Weight Period card's \"Import verified CSV\" section on Home.")
    else:
        st.dataframe(current_reference, width="stretch", height=min(450, 60 + 35 * len(current_reference)))
