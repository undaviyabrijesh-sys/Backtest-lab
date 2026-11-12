import pandas as pd
import pytest

from crypto_trader.skill_setups import rsi_wilder, scan_daily_setups


def frame(closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="D", tz="UTC"),
        "open": closes,
        "high": [x * 1.01 for x in closes],
        "low": [x * 0.99 for x in closes],
        "close": closes,
        "volume": [1000.0] * len(closes),
    })


def test_requires_minimum_history():
    assert scan_daily_setups(frame([100 + i for i in range(34)]), "BTCUSDT") == []


def test_breakout_20d_detected():
    closes = [100 + (i % 4) for i in range(79)] + [120]
    hits = scan_daily_setups(frame(closes), "BTCUSDT")
    assert "breakout_20d" in {x["setup"] for x in hits}


def test_bull_flag_detected():
    closes = [100.0] * 70
    closes += [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    closes += [117, 118, 117.5, 118.2, 117.8]
    hits = scan_daily_setups(frame(closes), "ETHUSDT")
    assert "bull_flag" in {x["setup"] for x in hits}


def test_rsi_wilder_bounds():
    values = rsi_wilder(pd.Series([100 + i for i in range(30)]))
    assert values.dropna().between(0, 100).all()


def test_bad_prices_rejected():
    data = frame([100 + i for i in range(40)])
    data.loc[0, "close"] = -1
    with pytest.raises(ValueError):
        scan_daily_setups(data, "BTCUSDT")


def test_bull_flag_range_includes_latest_completed_close():
    closes = [100.0] * 70
    closes += [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    closes += [117, 118, 117.5, 118.2, 130.0]
    hits = scan_daily_setups(frame(closes), "BTCUSDT")
    assert "bull_flag" not in {x["setup"] for x in hits}
