from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from india_day_trader.yahoo_source import normalize_yahoo_frame, yahoo_ticker

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(("symbol", "expected"), [
    ("NSE:NIFTY50-INDEX", "^NSEI"),
    ("NSE:NIFTYBANK-INDEX", "^NSEBANK"),
    ("BSE:SENSEX-INDEX", "^BSESN"),
    ("NSE:RELIANCE-EQ", "RELIANCE.NS"),
    ("BSE:RELIANCE-EQ", "RELIANCE.BO"),
])
def test_yahoo_symbol_mapping(symbol, expected):
    assert yahoo_ticker(symbol) == expected


def test_unknown_symbol_mapping_fails_closed():
    with pytest.raises(ValueError):
        yahoo_ticker("NSE:UNKNOWN")


def test_normalize_yahoo_frame_keeps_only_completed_today_bars():
    idx = pd.DatetimeIndex([
        pd.Timestamp("2026-11-11 09:15", tz=IST),
        pd.Timestamp("2026-11-11 09:20", tz=IST),
        pd.Timestamp("2026-11-11 09:25", tz=IST),
        pd.Timestamp("2026-11-10 15:20", tz=IST),
    ])
    frame = pd.DataFrame({
        "Open": [100, 101, 102, 99],
        "High": [101, 102, 103, 100],
        "Low": [99, 100, 101, 98],
        "Close": [100.5, 101.5, 102.5, 99.5],
        "Volume": [1000, 1100, 1200, 900],
    }, index=idx)
    now = datetime(2026, 11, 11, 9, 30, tzinfo=IST)
    bars = normalize_yahoo_frame(frame, now=now)
    assert len(bars) == 3
    assert list(bars.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert bars.iloc[-1]["close"] == 102.5


def test_normalize_yahoo_frame_drops_still_forming_bar():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-11-11 09:25", tz=IST)])
    frame = pd.DataFrame({
        "Open": [100], "High": [101], "Low": [99], "Close": [100.5], "Volume": [1000]
    }, index=idx)
    now = datetime(2026, 11, 11, 9, 29, tzinfo=IST)
    assert normalize_yahoo_frame(frame, now=now).empty
