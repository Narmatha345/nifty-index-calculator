"""Central paths and constants for the NIFTY Discrepancy Analysis tool."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

DATA_DIR = ROOT_DIR / "data"
REFERENCE_DIR = DATA_DIR / "reference"
CACHE_DIR = DATA_DIR / "cache"
PRICE_CACHE_DIR = CACHE_DIR / "prices"
WEIGHTS_CACHE_DIR = CACHE_DIR / "weights"
CACHE_META_PATH = CACHE_DIR / "meta.json"

TEMPLATES_DIR = ROOT_DIR / "templates"

# Optional, verified fallback import used only when the automatic NSE Indices
# fetch (see nifty_calc/weights.py) is unavailable. Never auto-populated with
# invented data - starts empty.
WEIGHTS_REFERENCE_PATH = REFERENCE_DIR / "nifty50_weights_history.csv"
WEIGHTS_REFERENCE_TEMPLATE_PATH = TEMPLATES_DIR / "weights_history_template.csv"

# Official NIFTY 50 index reference on Yahoo Finance.
OFFICIAL_INDEX_TICKER = "^NSEI"
INDEX_NAME = "NIFTY 50"

# NSE Indices (niftyindices.com) official source for full 50-constituent
# weightage. Published monthly (as-of the last trading day of each month) as
# "Market Capitalisation, Weightage, Beta for NIFTY 50 & NIFTY Next 50"
# (report type "2" in their Historical Data Reports tool). Confirmed
# available back to at least Jan 2010.
NSE_WEIGHTS_REPORT_ENDPOINT = "https://niftyindices.com/reports/historical-data/Index/"
NSE_WEIGHTS_REPORT_BASE_URL = "https://niftyindices.com"
NSE_WEIGHTS_REPORT_TYPE = "2"
NSE_WEIGHTS_EARLIEST_MONTH = "2010-01-01"

# NIFTY 50 ETFs available on yfinance (NSE-listed, tracking the NIFTY 50
# index). Verified directly against yfinance, not guessed. Configurable in
# the UI; NIFTYBEES is the oldest/most liquid and is the default.
ETF_TICKER_OPTIONS = {
    "NIFTYBEES.NS": "Nippon India ETF Nifty BeES",
    "SETFNIF50.NS": "SBI ETF Nifty 50",
    "HDFCNIFTY.NS": "HDFC Nifty 50 ETF",
}
DEFAULT_ETF_TICKER = "NIFTYBEES.NS"

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

CHART_RANGE_OPTIONS = ["1M", "3M", "6M", "1Y", "MAX", "Custom"]

# Threshold (absolute % difference between Calculated and Actual NIFTY) used
# to flag a date as an "unusually large" deviation in the discrepancy tables.
DEFAULT_DEVIATION_FLAG_PCT = 1.0
