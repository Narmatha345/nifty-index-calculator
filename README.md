# NIFTY Discrepancy Analysis Tool

Compares three time-series to identify where and when they diverge:

1. **Calculated NIFTY** - `Sum(Stock Price x Official NSE Weight)`, calibrated
   once against `^NSEI` at a chosen baseline date.
2. **Actual NIFTY 50** - the official index (`^NSEI`), fetched live from
   Yahoo Finance.
3. **NIFTY ETF** - a configurable NIFTY-tracking ETF's market price (e.g.
   NIFTYBEES.NS).

This is **not** an independent index reconstruction (no Shares Outstanding /
IWF / Divisor) and it does not label any series as "correct" - it exists to
surface discrepancy, not resolve it.

## Calculation model

**Weight Period vs Analysis Period are two separate controls.** The Weight
Period (e.g. "August 2026") selects one official NSE monthly weight snapshot;
that single snapshot is held constant across the entire Analysis Period,
however long it is or whichever months it spans - it is never silently
swapped for a different month's weights, and a month with no analysis-period
overlap with the weight period does not trigger a "missing data" warning.

1. For each date in the Analysis Period, `raw weighted value =
   Sum(Price[t] * OfficialWeight[t] / 100)` over the 50 constituents, using
   the ticker weights from the one selected **Weight Period** (see "Official
   weight data" below).
2. That raw value is calibrated **once**, at a user-chosen baseline date,
   against the official `^NSEI` value on that date:
   `normalization_factor = Official / Raw` at the baseline.
3. `Calculated NIFTY = raw weighted value * normalization_factor` for every
   date. The factor is fixed from the baseline date - it is never
   recalculated day-to-day.
4. Discrepancy = `Calculated - Actual` (absolute and %), with current/max/mean
   error, RMSE, the date of maximum deviation, and a table of dates where the
   deviation exceeds a configurable threshold.

(`nifty_calc/engine.py` also has a `build_weight_panel`/rolling-snapshot mode
used by the **Constituent Weights** page's weight-over-time browser, which
*does* roll forward across successive monthly snapshots - that's for
browsing weight history, not for the discrepancy calculation above.)

## Official weight data

NSE Indices (niftyindices.com) publishes **"Market Capitalisation, Weightage,
Beta for NIFTY 50 & NIFTY Next 50"** monthly - the official weight of all 50
constituents as of the last trading day of each month. This app fetches and
caches that report automatically (`nifty_calc/weights.py`); confirmed
available back to at least January 2010. No weight is ever invented: if NSE
can't be reached for a month, it's simply not offered as a Weight Period
option until a verified CSV covering it is imported via the **Reference Data
Manager** page (`templates/weights_history_template.csv` describes the exact
schema; the Manager also accepts NSE's raw `nifty50_mcwb.csv` export
directly - both formats are auto-detected).

The **Weight Period** selector (Home, Discrepancy History, Accuracy Metrics)
lists every month currently available locally (cached and/or imported) and
lets you fetch/check any other month on demand; picking one shows
"Official weight data is not available for this month." rather than
silently substituting a different month's data.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Run

```
streamlit run app/streamlit_app.py
```

## Pages

- **Home** - main dashboard: data period, ETF/baseline/interval controls,
  summary metrics, the three-line comparison chart (zoom/hover/range
  buttons/rangeslider), discrepancy table, constituent weight table, and a
  data source/status panel.
- **Discrepancy History** - Calculated vs Actual vs ETF over any date range,
  with CSV export.
- **Constituent Weights** - the official weight of every constituent as of a
  chosen date, plus a weight-over-time chart for selected stocks.
- **Accuracy Metrics** - discrepancy statistics (current/mean/RMSE/max) and a
  table of unusually large deviations over a chosen range.
- **Reference Data Manager** - check/refresh the auto-fetched NSE weight
  data, and import a verified fallback CSV for any month NSE couldn't be
  reached for.

## Project layout

```
config.py              paths and constants (ETF options, NSE endpoint, etc.)
nifty_calc/
  weights.py             official NSE weight fetch/cache/parse + history lookups
  price_data.py          yfinance batch download + local parquet cache
  engine.py               pure calculation functions (weighting, baseline
                          calibration, discrepancy metrics) - no I/O/UI
  validation.py           missing-data readiness checks
  ssl_bootstrap.py        optional local CA trust fix (see certs/README.md)
data/reference/           verified fallback weight CSV (starts empty)
data/cache/               auto-fetched price + weight cache (gitignored)
templates/                annotated, empty CSV template for the fallback import
app/                      Streamlit UI (Home.py + pages/)
tests/                    unit tests for weights parsing + the calculation engine
```

## Notes

- Price data is cached locally in `data/cache/prices/` as Parquet files;
  weight data in `data/cache/weights/` as CSVs - both refreshed
  incrementally, not re-downloaded on every run.
- `certs/local_root_ca.pem`, if present, lets `yfinance`/`requests` work on
  machines where antivirus/corporate software intercepts HTTPS traffic (see
  `certs/README.md`). It's a no-op on machines that don't need it.
