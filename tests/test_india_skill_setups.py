import pandas as pd
import pytest

from india_day_trader.skill_setups import rsi_wilder, scan_daily_setups


def frame(closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="B"),
        "open": closes,
        "high": [x * 1.01 for x in closes],
        "low": [x * 0.99 for x in closes],
        "close": closes,
        "volume": [100000.0] * len(closes),
    })


def names(hits):
    return {item["setup"] for item in hits}


def test_requires_35_completed_sessions():
    assert scan_daily_setups(frame([100 + i for i in range(34)]), "RELIANCE.NS") == []


def test_20_session_close_breakout():
    closes = [100 + (i % 4) for i in range(79)] + [120]
    hits = scan_daily_setups(frame(closes), "RELIANCE.NS")
    assert "breakout_20d" in names(hits)
    assert all(hit["market"] == "INDIA_CASH_EQUITY" for hit in hits)


def test_bull_flag_pattern():
    closes = [100.0] * 70
    closes += [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    closes += [117, 118, 117.5, 118.2, 117.8]
    assert "bull_flag" in names(scan_daily_setups(frame(closes), "TCS.NS"))


def test_latest_close_is_in_bull_flag_consolidation():
    closes = [100.0] * 70
    closes += [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    closes += [117, 118, 117.5, 118.2, 130.0]
    assert "bull_flag" not in names(scan_daily_setups(frame(closes), "INFY.NS"))


def test_rsi_wilder_is_bounded():
    result = rsi_wilder(pd.Series([100 + i for i in range(30)]))
    assert result.dropna().between(0, 100).all()


def test_invalid_prices_and_negative_volume_rejected():
    data = frame([100 + i for i in range(40)])
    data.loc[0, "close"] = -1
    with pytest.raises(ValueError):
        scan_daily_setups(data, "SBIN.NS")
    data = frame([100 + i for i in range(40)])
    data.loc[0, "volume"] = -1
    with pytest.raises(ValueError):
        scan_daily_setups(data, "SBIN.NS")


def test_index_symbol_is_classified_and_scanned():
    closes = [100 + (i % 4) for i in range(79)] + [120]
    hits = scan_daily_setups(frame(closes), "NSE:NIFTY50-INDEX")
    assert hits
    assert all(x["market"] == "INDIA_INDEX" for x in hits)
    assert all(x["symbol"] == "NSE:NIFTY50-INDEX" for x in hits)


def test_index_can_be_explicitly_classified():
    closes = [100 + (i % 4) for i in range(79)] + [120]
    hits = scan_daily_setups(frame(closes), "BANKNIFTY", market="INDIA_INDEX")
    assert hits and all(x["market"] == "INDIA_INDEX" for x in hits)


def test_invalid_market_type_rejected():
    with pytest.raises(ValueError):
        scan_daily_setups(frame([100 + i for i in range(40)]), "NIFTY", market="OPTIONS")


def test_candidates_are_research_only_and_long_only():
    hits = scan_daily_setups(frame([100 + (i % 4) for i in range(79)] + [120]), "HDFCBANK.NS")
    assert hits
    assert all(x["status"] == "RESEARCH_CANDIDATE" and x["side"] == "LONG" for x in hits)
    assert all("stop" not in x and "target" not in x and "quantity" not in x for x in hits)
