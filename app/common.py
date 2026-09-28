"""Shared Streamlit helpers: cached data loaders reused across pages so
every page sees the same reference/price data and cache."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from nifty_calc import price_data, weights

RANGE_TO_TIMEDELTA = {
    "1M": pd.Timedelta(days=30),
    "3M": pd.Timedelta(days=90),
    "6M": pd.Timedelta(days=182),
    "1Y": pd.Timedelta(days=365),
}

RESAMPLE_RULE = {"Daily": None, "Weekly": "W-FRI", "Monthly": "ME"}


@st.cache_data(ttl=3600)
def load_weights_history(start, end):
    """Official NIFTY 50 weight history for [start, end]: auto-fetched from
    NSE Indices and cached (see nifty_calc/weights.py). Returns
    (history_df, missing_months)."""
    return weights.get_history(start, end)


@st.cache_data(ttl=300)
def load_price_history(tickers: tuple, start, end, interval: str = "1d"):
    """tickers should already include everything the caller wants fetched
    (constituents + ^NSEI + the selected ETF, etc.) - this does not add any
    tickers implicitly."""
    data, interval_used = price_data.get_prices(list(tickers), start, end, interval)
    return data, interval_used


def resolve_range(range_choice: str, custom_start=None, custom_end=None):
    """Turn a CHART_RANGE_OPTIONS choice into concrete (start, end) timestamps."""
    if range_choice == "Custom":
        return pd.Timestamp(custom_start), pd.Timestamp(custom_end)
    if range_choice == "MAX":
        return pd.Timestamp(config.NSE_WEIGHTS_EARLIEST_MONTH), pd.Timestamp.today().normalize()
    end_date = pd.Timestamp.today().normalize()
    start_date = end_date - RANGE_TO_TIMEDELTA[range_choice]
    return start_date, end_date


def resample_series(df: pd.DataFrame, interval_choice: str) -> pd.DataFrame:
    """Optionally resample a date-indexed DataFrame to a coarser resolution
    (last observation of each period) for the "Data interval" control."""
    rule = RESAMPLE_RULE.get(interval_choice)
    if rule is None:
        return df
    return df.resample(rule).last().dropna(how="all")


@st.cache_resource
def _shared_inputs_store() -> dict:
    """A singleton dict shared by every session/page in this running server
    process (st.cache_resource, not st.cache_data - it holds a live object,
    not a serializable result). st.session_state can't be used for this: in
    this app, clicking a sidebar nav link is a real browser navigation to
    that page's own URL, which starts a brand-new Streamlit session with
    empty session_state - it does not carry over from Home. This app is
    single-user/local, so a process-wide singleton is the right tool: Home
    writes the resolved inputs here once per rerun, and any other page
    (even after a hard navigation) reads the same values back."""
    return {}


def set_home_inputs(**kwargs) -> None:
    """Called by Home after it resolves its sidebar inputs, so other pages
    can read the exact same Weight Period / Analysis Period / ETF / Baseline
    / Deviation-flag values without asking for them again."""
    _shared_inputs_store().update(kwargs)


def read_home_inputs():
    """The shared set of analysis inputs (Weight Period, Analysis Period,
    ETF, Baseline, Deviation flag) last resolved on the Home page. Detail
    pages (Discrepancy History, Accuracy Metrics) call this instead of
    rendering their own copies of the same inputs, so there is exactly one
    place in the app where these get set. Returns None if Home hasn't run at
    least once yet in this server process."""
    store = _shared_inputs_store()
    if "selected_period" not in store or "start_ts" not in store:
        return None
    return dict(store)


def render_home_inputs_recap(inputs: dict) -> None:
    """Read-only recap of the shared inputs a detail page is using, with a
    link back to Home to change them - so the page is self-explanatory
    without needing its own copies of the same controls."""
    st.page_link("Home.py", label="Change inputs on Home", icon=":material/tune:")
    period_label = weights.format_period_label(inputs["selected_period"])
    range_label = f'{inputs["start_ts"].date()} &rarr; {inputs["end_ts"].date()}'
    pills = [
        render_pill(f"Weight period &nbsp;<b>{period_label}</b>"),
        render_pill(f"Analysis period &nbsp;<b>{range_label}</b>", neutral=True),
        render_pill(f'ETF &nbsp;<b>{inputs["etf_ticker"]}</b>', neutral=True),
        render_pill(f'Baseline &nbsp;<b>{inputs["baseline_date"]}</b>', neutral=True),
    ]
    st.markdown("&nbsp;".join(pills), unsafe_allow_html=True)
    st.write("")


# --------------------------------------------------------------------------
# Presentation helpers (styling only - no calculation/data logic below).
# --------------------------------------------------------------------------

_HERO_SVG = """
<svg width="190" height="150" viewBox="0 0 190 150" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Rising trend illustration">
    <rect x="14" y="88" width="26" height="52" rx="7" fill="#C7D2FE"/>
    <rect x="56" y="64" width="26" height="76" rx="7" fill="#A5B4FC"/>
    <rect x="98" y="38" width="26" height="102" rx="7" fill="#818CF8"/>
    <rect x="140" y="16" width="26" height="124" rx="7" fill="#6366F1"/>
    <polyline points="14,96 56,68 98,44 140,20 176,8" fill="none" stroke="#22C55E" stroke-width="4"
              stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="176" cy="8" r="7" fill="#22C55E"/>
</svg>
"""

_CSS = """
<style>
.stApp { overflow-x: hidden; }

/* Sidebar nav: active-item gradient pill + hover + spacing */
[data-testid="stSidebarNav"] a {
    border-radius: 0.75rem;
    margin: 0.15rem 0.75rem;
    padding: 0.55rem 0.9rem !important;
    transition: background 200ms ease, color 200ms ease;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(129, 140, 248, 0.16);
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: linear-gradient(135deg, #6366F1, #818CF8);
}
[data-testid="stSidebarNav"] a[aria-current="page"] span,
[data-testid="stSidebarNav"] a[aria-current="page"] p {
    color: #FFFFFF !important;
}

/* Alert cards (Missing Data / Info / Warning) */
.nifty-alert {
    display: flex;
    gap: 0.85rem;
    align-items: flex-start;
    border-radius: 1rem;
    border: 1px solid var(--nifty-alert-border);
    background: var(--nifty-alert-bg);
    padding: 1.1rem 1.25rem;
    margin-bottom: 1rem;
}
.nifty-alert-icon {
    flex-shrink: 0;
    width: 2rem;
    height: 2rem;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.05rem;
    font-weight: 700;
    color: #FFFFFF;
    background: var(--nifty-alert-icon-bg);
}
.nifty-alert-title {
    font-weight: 700;
    font-size: 0.78rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
    color: var(--nifty-alert-title-color);
}
.nifty-alert-body { color: #1E293B; line-height: 1.55; font-size: 0.95rem; }

.nifty-alert-error {
    --nifty-alert-bg: #FEF2F4;
    --nifty-alert-border: #FBCFD8;
    --nifty-alert-icon-bg: #EF4444;
    --nifty-alert-title-color: #B91C1C;
}
.nifty-alert-info {
    --nifty-alert-bg: #EFF4FF;
    --nifty-alert-border: #C7D9FB;
    --nifty-alert-icon-bg: #3B82F6;
    --nifty-alert-title-color: #1D4ED8;
}
.nifty-alert-warning {
    --nifty-alert-bg: #FFF8EB;
    --nifty-alert-border: #FBE3AE;
    --nifty-alert-icon-bg: #F59E0B;
    --nifty-alert-title-color: #B45309;
}

/* Top-right header row */
.nifty-header-row {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1.25rem;
}
.nifty-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: #16A34A;
    background: #ECFDF5;
    border: 1px solid #BBF7D0;
    padding: 0.3rem 0.75rem;
    border-radius: 999px;
}
.nifty-badge-dot { width: 0.45rem; height: 0.45rem; border-radius: 999px; background: #22C55E; }

/* Home hero */
.nifty-hero { display: flex; align-items: center; gap: 2rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.nifty-hero-text { flex: 1 1 340px; min-width: 280px; }
.nifty-hero-badge {
    display: inline-block; font-size: 0.78rem; font-weight: 600; color: #4F46E5;
    background: #EEF2FF; border: 1px solid #E0E7FF; padding: 0.3rem 0.85rem;
    border-radius: 999px; margin-bottom: 0.9rem;
}
.nifty-hero-title { font-size: 2.6rem; font-weight: 800; line-height: 1.1; color: #0F172A; margin: 0 0 0.6rem 0; }
.nifty-hero-title .grad {
    background: linear-gradient(135deg, #6366F1, #3B82F6);
    -webkit-background-clip: text; background-clip: text; color: transparent;
}
.nifty-hero-subtitle { color: #475569; font-size: 1.02rem; max-width: 42rem; line-height: 1.5; }
.nifty-hero-art { flex: 0 0 190px; }

/* Sidebar footer */
.nifty-sidebar-footer { color: #64748B; font-size: 0.75rem; padding: 1rem 0.6rem; text-align: center; }

/* ---- Card containers: any st.container(border=True) becomes a themed card.
   Sidebar cards get the dark-sidebar treatment; main-content cards get a
   soft-shadow light card - purely presentational grouping for related
   inputs/sections, no effect on what each card actually contains. */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 1.1rem !important;
    transition: border-color 150ms ease;
}

[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: #141B2E !important;
    border: 1px solid rgba(129, 140, 248, 0.20) !important;
    padding: 0.15rem 0.2rem 0.5rem 0.2rem;
    margin-bottom: 0.85rem;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]:has(input:focus),
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(129, 140, 248, 0.45) !important;
}
[data-testid="stSidebar"] h3 {
    font-size: 0.86rem !important;
    letter-spacing: 0.02em;
    color: #E0E7FF !important;
    margin-bottom: 0.4rem !important;
}

section[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF;
    border: 1px solid #E7EAF3 !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03), 0 14px 32px -22px rgba(15, 23, 42, 0.22);
    padding: 1.5rem 1.6rem 1.6rem 1.6rem;
    margin-bottom: 1.6rem;
}
section[data-testid="stMain"] h3 {
    font-weight: 700 !important;
    color: #0F172A;
}

/* Metric tiles - used for Summary / Discrepancy / Accuracy stat rows */
[data-testid="stMetric"] {
    background: #F8FAFC;
    border: 1px solid #EEF2F7;
    border-radius: 0.9rem;
    padding: 0.95rem 1.1rem 0.8rem 1.1rem;
}
[data-testid="stMetricLabel"] { font-size: 0.78rem; color: #64748B; }
[data-testid="stMetricValue"] { font-size: 1.5rem; }

/* Buttons */
.stButton > button, .stDownloadButton > button {
    border-radius: 999px;
    font-weight: 600;
    transition: transform 120ms ease, box-shadow 120ms ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); }
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366F1, #818CF8);
    border: none;
}

/* Small status/count pill, e.g. next to a card header */
.nifty-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.24rem 0.7rem;
    border-radius: 999px;
    background: #EEF2FF;
    color: #4F46E5;
    border: 1px solid #E0E7FF;
    white-space: nowrap;
}
.nifty-pill-neutral { background: #F1F5F9; color: #475569; border-color: #E2E8F0; }

/* Card header row: title (native st.subheader) + trailing pill, side by side */
.nifty-card-header-row { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: -0.6rem; flex-wrap: wrap; }

/* Sidebar caption text - lighten to match dark sidebar */
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #94A3B8 !important; }

/* Date-picker calendar popup: day cells render as
   <div role="button" data-rac="">28</div> (React Aria Components). This used
   to need a forced light-text override back when these date inputs lived in
   the dark sidebar (the popup inherited a dark background there, making the
   default near-black day-number text invisible). Now that all inputs moved
   to the main page's white-background area, the popup is white and the
   library's own default dark text is already correctly readable - no
   override needed. (Kept as a comment so the history isn't lost: forcing a
   light color here again would make the text invisible against this white
   popup instead.) */

@media (max-width: 640px) {
    .nifty-hero-title { font-size: 1.9rem; }
    .nifty-hero-art { display: none; }
    .nifty-header-row { justify-content: space-between; }
}
</style>
"""


def inject_css() -> None:
    """App-wide styling for the fintech-dashboard redesign. Presentation only -
    does not touch any calculation, data-loading, or validation logic."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_top_header() -> None:
    st.markdown(
        """
        <div class="nifty-header-row">
            <span class="nifty-badge"><span class="nifty-badge-dot"></span>NIFTY 50 Analytics</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_alert(kind: str, title: str, icon: str, text: str) -> None:
    st.markdown(
        f"""
        <div class="nifty-alert nifty-alert-{kind}">
            <div class="nifty-alert-icon">{icon}</div>
            <div>
                <div class="nifty-alert-title">{title}</div>
                <div class="nifty-alert-body">{text}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_missing_data_alert(text: str) -> None:
    """Styled replacement for st.error() on the validation.check_readiness()
    banner - same message text/trigger, presentation only."""
    _render_alert("error", "Missing Data", "!", text)


def render_info_alert(text: str) -> None:
    """Styled replacement for st.info() - same message text, presentation only."""
    _render_alert("info", "Info", "i", text)


def render_warning_alert(text: str) -> None:
    """Styled replacement for st.warning() on the validation.check_readiness()
    banner - same message text/trigger, presentation only."""
    _render_alert("warning", "Warning", "!", text)


def render_hero(subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="nifty-hero">
            <div class="nifty-hero-text">
                <span class="nifty-hero-badge">Welcome</span>
                <h1 class="nifty-hero-title">{config.INDEX_NAME} <span class="grad">Calculator</span></h1>
                <p class="nifty-hero-subtitle">{subtitle}</p>
            </div>
            <div class="nifty-hero-art">{_HERO_SVG}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def inject_sidebar_shell_css() -> None:
    """Pins the sidebar footer (rendered via render_sidebar_footer) to the
    bottom of the sidebar, below the nav widget, regardless of content
    height. The logo itself is rendered via the native st.logo() API
    (see streamlit_app.py), which Streamlit places above the nav widget."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebarContent"] { display: flex; flex-direction: column; height: 100%; }
        [data-testid="stSidebarUserContent"] { margin-top: auto; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_pill(text: str, neutral: bool = False) -> str:
    """A small rounded status/count pill, e.g. "50 constituents". Returns the
    HTML snippet (caller embeds it, often next to a card's st.subheader)."""
    cls = "nifty-pill nifty-pill-neutral" if neutral else "nifty-pill"
    return f'<span class="{cls}">{text}</span>'


def render_sidebar_footer() -> None:
    st.markdown(
        '<div class="nifty-sidebar-footer">Analyze &middot; Explore &middot; Build Better Insights</div>',
        unsafe_allow_html=True,
    )
