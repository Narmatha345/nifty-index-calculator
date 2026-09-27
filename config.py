"""Central paths and constants for the NIFTY Index Calculator."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

DATA_DIR = ROOT_DIR / "data"
REFERENCE_DIR = DATA_DIR / "reference"
CACHE_DIR = DATA_DIR / "cache"
PRICE_CACHE_DIR = CACHE_DIR / "prices"
CACHE_META_PATH = CACHE_DIR / "meta.json"

TEMPLATES_DIR = ROOT_DIR / "templates"

CONSTITUENTS_PATH = REFERENCE_DIR / "constituents.csv"
DIVISOR_HISTORY_PATH = REFERENCE_DIR / "divisor_history.csv"
PUBLISHED_WEIGHTS_PATH = REFERENCE_DIR / "published_weights.csv"

CONSTITUENTS_TEMPLATE_PATH = TEMPLATES_DIR / "constituents_template.csv"
DIVISOR_HISTORY_TEMPLATE_PATH = TEMPLATES_DIR / "divisor_history_template.csv"
PUBLISHED_WEIGHTS_TEMPLATE_PATH = TEMPLATES_DIR / "published_weights_template.csv"

# Official NIFTY 50 index reference on Yahoo Finance.
OFFICIAL_INDEX_TICKER = "^NSEI"
INDEX_NAME = "NIFTY 50"

# yfinance interval fallback order, richest resolution first.
INTERVAL_FALLBACK_ORDER = ["1m", "5m", "15m", "1h", "1d"]

# Approximate maximum lookback (in days) yfinance/Yahoo will serve for each
# intraday interval. These are practical limits, not guarantees; price_data
# still detects empty/short responses and falls back further.
INTERVAL_MAX_LOOKBACK_DAYS = {
    "1m": 7,
    "5m": 60,
    "15m": 60,
    "1h": 730,
    "1d": None,  # effectively unlimited
}

CHART_RANGE_OPTIONS = ["1D", "5D", "1M", "3M", "6M", "1Y", "MAX", "Custom"]
