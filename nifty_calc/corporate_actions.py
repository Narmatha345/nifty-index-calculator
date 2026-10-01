"""Bridges the symbols in NSE's official weight files to the price series
Yahoo Finance actually serves, accounting for corporate actions between a
weight snapshot's as-of date and the dates being analysed. Pure functions -
no I/O.

Yahoo's `Close` is already adjusted for splits and bonus issues, so those
need nothing here. What does need handling:

  * Renames / mergers - an NSE weight file lists the symbol as it was on
    its as-of date, but Yahoo serves the full history only under the
    current symbol (TICKER_ALIASES).
  * Demergers - on the ex-date the parent's price drops by the value of
    the spun-off business, which Yahoo does NOT adjust for. NSE carries that
    value in the index as a dummy constituent held at a constant price
    (DEMERGERS). A basket anchored on one side of the ex-date has to be
    expressed on the same basis on the other side, or the drop shows up as
    a phantom index move.
"""

from __future__ import annotations

import pandas as pd

# NSE weight-file symbol -> Yahoo symbol that carries its full price history.
TICKER_ALIASES = {
    "TATAMOTORS.NS": "TMPV.NS",  # renamed Tata Motors Passenger Vehicles after the Oct-2025 CV demerger
    "ZOMATO.NS": "ETERNAL.NS",  # renamed Eternal Ltd. (Mar-2025)
    "LTIM.NS": "LTM.NS",
    # HDFC Ltd. merged into HDFC Bank effective 13-Jul-2023 (42 HDFCBANK shares
    # per 25 HDFC) and Yahoo dropped HDFC.NS. The calculation only uses price
    # relatives (price / anchor price), in which a fixed swap ratio cancels
    # out, so HDFC Bank's series stands in for it directly.
    "HDFC.NS": "HDFCBANK.NS",
}

# Demergers NSE handled with a dummy constituent. dummy_price is the
# spun-off business's value per parent share: the parent's close on the day
# before ex_date minus its price-discovery price on ex_date. Both values
# below also match the dummy price implied by NSE's own month-end weights
# (dummy weight / parent weight x parent close).
DEMERGERS = [
    {
        # Tata Motors -> TMCV (commercial vehicles): 660.75 - 400.00
        "parent": "TMPV.NS",
        "ex_date": pd.Timestamp("2025-10-14"),
        "dummy": "DUMMYTATAM.NS",
        "dummy_price": 260.75,
    },
    {
        # Hindustan Unilever -> Kwality Wall's (ice cream): 2462.20 - 2422.00
        "parent": "HINDUNILVR.NS",
        "ex_date": pd.Timestamp("2025-12-05"),
        "dummy": "DUMMYHDLVR.NS",
        "dummy_price": 40.20,
    },
]

_DUMMY_PRICES = {d["dummy"]: d["dummy_price"] for d in DEMERGERS}


def price_source(ticker: str) -> str | None:
    """The Yahoo symbol to fetch for an NSE weight-file symbol, or None for
    an NSE dummy constituent (no market price - held constant by NSE)."""
    if ticker in _DUMMY_PRICES:
        return None
    return TICKER_ALIASES.get(ticker, ticker)


def price_sources(tickers) -> list[str]:
    """Every Yahoo symbol needed to price `tickers`, deduplicated."""
    return sorted({src for src in (price_source(t) for t in tickers) if src is not None})


def build_constituent_close_panel(tickers, price_dict: dict[str, pd.DataFrame], as_of_date, price_col: str = "Close") -> pd.DataFrame:
    """[date x weight-file ticker] close prices, expressed on the share basis
    in force on `as_of_date` (the weight snapshot's date):

      * aliased symbols are read from their current Yahoo symbol;
      * a demerger parent is shifted by the dummy price across its ex-date -
        +dummy after it when the snapshot predates the demerger (the basket
        still holds the spun-off business), -dummy before it when the
        snapshot postdates it (the basket holds only the remaining business);
      * an NSE dummy constituent is held at its constant dummy price;
      * zero-volume placeholder bars are treated as missing (NaN).

    Columns with no price data at all are dropped, so the caller's coverage
    figure reflects them."""
    as_of = pd.Timestamp(as_of_date)
    series: dict[str, pd.Series] = {}
    for ticker in tickers:
        src = price_source(ticker)
        if src is None:
            continue
        df = price_dict.get(src)
        if df is None or df.empty or price_col not in df.columns:
            continue
        s = df[price_col].astype(float).copy()
        if "Volume" in df.columns:
            # Yahoo sometimes serves a placeholder bar (volume 0, previous
            # close repeated) for a session it has no data for - e.g. every
            # NSE stock on 2025-03-18. That's a missing price, not a price.
            s[df["Volume"] == 0] = float("nan")
        for d in DEMERGERS:
            if d["parent"] != src:
                continue
            if as_of < d["ex_date"]:
                s.loc[s.index >= d["ex_date"]] += d["dummy_price"]
            else:
                s.loc[s.index < d["ex_date"]] -= d["dummy_price"]
        series[ticker] = s

    if not series:
        return pd.DataFrame()
    panel = pd.DataFrame(series).sort_index()

    for ticker in tickers:
        if ticker in _DUMMY_PRICES:
            panel[ticker] = _DUMMY_PRICES[ticker]
    return panel
