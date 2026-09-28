"""Entrypoint for the redesigned app shell: defines navigation (with icons)
and the sidebar logo/footer. Run with `streamlit run app/streamlit_app.py`.

Each page file's own business logic, data loading, and calculations are
completely untouched - this module only wires up navigation and wraps it
with presentation. `url_path` is pinned to each page's pre-existing route
so no links break.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import inject_sidebar_shell_css, render_sidebar_footer

home = st.Page("Home.py", title="Home", icon=":material/home:", url_path="Home", default=True)
discrepancy_history = st.Page(
    "pages/1_Discrepancy_History.py",
    title="Discrepancy History",
    icon=":material/calendar_month:",
    url_path="Discrepancy_History",
)
constituent_weights = st.Page(
    "pages/2_Constituent_Weights.py",
    title="Constituent Weights",
    icon=":material/table_chart:",
    url_path="Constituent_Weights",
)
accuracy = st.Page(
    "pages/4_Accuracy_Metrics.py",
    title="Accuracy Metrics",
    icon=":material/track_changes:",
    url_path="Accuracy_Metrics",
)
reference_data_manager = st.Page(
    "pages/5_Reference_Data_Manager.py",
    title="Reference Data Manager",
    icon=":material/database:",
    url_path="Reference_Data_Manager",
)

st.logo(str(Path(__file__).resolve().parent / "assets" / "sidebar_logo.svg"), size="large")

inject_sidebar_shell_css()
with st.sidebar:
    render_sidebar_footer()

pg = st.navigation(
    [home, discrepancy_history, constituent_weights, accuracy, reference_data_manager],
    position="sidebar",
)
pg.run()
