"""Shared Streamlit helpers: cached data loaders reused across pages so
every page sees the same reference/price data and cache."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from nifty_calc import divisor as divisor_mod
from nifty_calc import price_data, reference_data

RANGE_TO_TIMEDELTA = {
    "1D": pd.Timedelta(days=1),
    "5D": pd.Timedelta(days=5),
    "1M": pd.Timedelta(days=30),
    "3M": pd.Timedelta(days=90),
    "6M": pd.Timedelta(days=182),
    "1Y": pd.Timedelta(days=365),
}


@st.cache_data(ttl=300)
def load_reference_data():
    constituents = reference_data.load_constituents()
    divisor_hist = divisor_mod.load_divisor_history()
    return constituents, divisor_hist


@st.cache_data(ttl=300)
def load_published_weights():
    return reference_data.load_published_weights()


@st.cache_data(ttl=300)
def load_price_history(tickers: tuple, start, end, interval: str):
    all_tickers = list(tickers) + [config.OFFICIAL_INDEX_TICKER]
    data, interval_used = price_data.get_prices(all_tickers, start, end, interval)
    return data, interval_used


def resolve_range(range_choice: str, custom_start=None, custom_end=None):
    """Turn a CHART_RANGE_OPTIONS choice into concrete (start, end) timestamps."""
    if range_choice == "Custom":
        return pd.Timestamp(custom_start), pd.Timestamp(custom_end)
    if range_choice == "MAX":
        return pd.Timestamp("2000-01-01"), pd.Timestamp.today().normalize()
    end_date = pd.Timestamp.today().normalize()
    start_date = end_date - RANGE_TO_TIMEDELTA[range_choice]
    return start_date, end_date


def default_interval_for_range(range_choice: str) -> str:
    if range_choice == "1D":
        return "1m"
    if range_choice == "5D":
        return "5m"
    return "1d"


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
.nifty-avatar {
    width: 2.1rem; height: 2.1rem; border-radius: 999px;
    background: linear-gradient(135deg, #6366F1, #818CF8);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.9rem;
}
.nifty-caret { color: #94A3B8; font-size: 0.75rem; }

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
            <span class="nifty-avatar">N</span>
            <span class="nifty-caret">&#9662;</span>
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


def render_sidebar_footer() -> None:
    st.markdown(
        '<div class="nifty-sidebar-footer">Analyze &middot; Explore &middot; Build Better Insights</div>',
        unsafe_allow_html=True,
    )
