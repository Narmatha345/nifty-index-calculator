# NIFTY 50 Index Calculator

Independently reconstructs the NIFTY 50 index from free-float market cap
(`Price x Shares x IWF`, summed and divided by a divisor), rather than by
replaying the officially published index returns or weights. Compares the
result to the official `^NSEI` value live and across history.

## Why the app may show "MISSING DATA"

Shares outstanding, Investible Weight Factor (IWF), historical NIFTY 50
membership, and the index divisor are NSE-proprietary reference data. **This
app never invents these values.** It ships with empty, annotated templates
(`templates/*.csv`) and will show a clear MISSING DATA banner instead of a
calculated number until you supply real data.

Source real values from official NSE index factsheets / methodology
documents, then import them via the **Reference Data Manager** page in the
app (or by editing `data/reference/*.csv` directly, using the same schema as
the templates).

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

## Load reference data

1. Open the **Reference Data Manager** page (left sidebar).
2. Download the constituent and divisor-history templates, fill them in with
   verified real data (see the comments inside each template for the exact
   field meanings and the divisor calibration formula), and upload them back.
3. Optionally supply `published_weights.csv` to see the official/reference
   NIFTY weight next to this app's independently calculated weight in the
   Constituent Table.
4. Use the "Calibrate a new divisor" tool once you have constituent data
   loaded and a date where official `^NSEI` and constituent prices are both
   available. After that, the calculated index runs independently - the app
   does not keep re-calibrating against `^NSEI`.

## Pages

- **Home** - live dashboard: Official vs Calculated NIFTY, difference, and a
  range-selectable comparison chart (1D/5D/1M/3M/6M/1Y/MAX/Custom).
- **Historical Reconstruction** - calculated vs official index across any
  date range, with CSV export.
- **Constituent Table** - per-stock price, shares, IWF, free-float market
  cap, calculated weight, price change, and point contribution, as of a
  chosen date.
- **Contribution Analysis** - which stocks drove the calculated index's move
  over a date range; contributions reconcile exactly to the total change.
- **Accuracy Metrics** - current error, MAE, RMSE, and max error between the
  calculated and official index over a selected history.
- **Reference Data Manager** - import/validate constituent, divisor, and
  published-weight CSVs; run one-time divisor calibration.

## Project layout

```
config.py              paths and constants
nifty_calc/
  schemas.py            reference-data schemas/validation
  reference_data.py     time-varying constituents (shares/IWF/membership)
  divisor.py             divisor history + calibration
  price_data.py          yfinance batch download + local parquet cache
  engine.py               pure index-calculation functions (no I/O/UI)
  validation.py           missing-data readiness checks
  ssl_bootstrap.py        optional local CA trust fix (see certs/README.md)
data/reference/           active CSV reference data (starts empty)
templates/                annotated, empty CSV templates
app/                      Streamlit UI (Home.py + pages/)
tests/                    unit tests for the calculation engine
```

## Notes

- Price data is cached locally in `data/cache/` as Parquet files, refreshed
  incrementally (only the missing date range is re-downloaded).
- If a requested chart resolution (e.g. 1-minute) isn't available from
  Yahoo Finance for the selected range, the app automatically falls back to
  a coarser resolution and labels which one is being shown.
- `certs/local_root_ca.pem`, if present, lets `yfinance` work on machines
  where antivirus/corporate software intercepts HTTPS traffic (see
  `certs/README.md`). It's a no-op on machines that don't need it.
