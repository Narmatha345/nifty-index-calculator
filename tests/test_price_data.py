import pandas as pd

import config
from nifty_calc import price_data


def _ohlc(dates) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"Close": range(1, len(idx) + 1)}, index=idx, dtype=float)


def _fake_download(available: dict[str, pd.DataFrame], calls: list):
    def download(tickers, start, end, **kwargs):
        calls.append((list(tickers), pd.Timestamp(start), pd.Timestamp(end)))
        frames = {t: df.loc[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))] for t, df in available.items() if t in tickers}
        return pd.concat(frames, axis=1)

    return download


def _use_tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PRICE_CACHE_DIR", tmp_path / "prices")
    monkeypatch.setattr(config, "CACHE_META_PATH", tmp_path / "meta.json")


def test_stock_listed_after_range_start_is_not_redownloaded(monkeypatch, tmp_path):
    _use_tmp_cache(monkeypatch, tmp_path)
    available = {
        "OLD.NS": _ohlc(["2024-01-01", "2024-06-03", "2024-12-31"]),
        "NEW.NS": _ohlc(["2024-06-03", "2024-12-31"]),  # listed mid-range
    }
    calls = []
    monkeypatch.setattr(price_data.yf, "download", _fake_download(available, calls))

    first = price_data.download_batch(["OLD.NS", "NEW.NS"], "2024-01-01", "2024-12-31", "1d")
    second = price_data.download_batch(["OLD.NS", "NEW.NS"], "2024-01-01", "2024-12-31", "1d")

    assert len(calls) == 1
    assert len(first["NEW.NS"]) == 2 and len(second["NEW.NS"]) == 2


def test_only_the_missing_earlier_slice_is_fetched(monkeypatch, tmp_path):
    _use_tmp_cache(monkeypatch, tmp_path)
    available = {"A.NS": _ohlc(["2023-01-02", "2023-06-01", "2024-01-01", "2024-06-03"])}
    calls = []
    monkeypatch.setattr(price_data.yf, "download", _fake_download(available, calls))

    price_data.download_batch(["A.NS"], "2024-01-01", "2024-06-30", "1d")
    out = price_data.download_batch(["A.NS"], "2023-01-01", "2024-06-30", "1d")

    assert len(calls) == 2
    assert calls[1][1] == pd.Timestamp("2023-01-01")
    assert calls[1][2] <= pd.Timestamp("2024-01-02")
    assert len(out["A.NS"]) == 4


def test_failed_request_is_not_recorded_as_covered(monkeypatch, tmp_path):
    _use_tmp_cache(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(price_data.yf, "download", lambda tickers, start, end, **kw: calls.append(1) or pd.DataFrame())

    price_data.download_batch(["A.NS"], "2024-01-01", "2024-06-30", "1d")
    price_data.download_batch(["A.NS"], "2024-01-01", "2024-06-30", "1d")

    assert len(calls) == 2
