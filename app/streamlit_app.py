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
historical = st.Page(
    "pages/1_Historical_Reconstruction.py",
    title="Historical Reconstruction",
    icon=":material/calendar_month:",
    url_path="Historical_Reconstruction",
)
constituent_table = st.Page(
    "pages/2_Constituent_Table.py",
    title="Constituent Table",
    icon=":material/table_chart:",
    url_path="Constituent_Table",
)
contribution = st.Page(
    "pages/3_Contribution_Analysis.py",
    title="Contribution Analysis",
    icon=":material/pie_chart:",
    url_path="Contribution_Analysis",
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
    [home, historical, constituent_table, contribution, accuracy, reference_data_manager],
    position="sidebar",
)
pg.run()
