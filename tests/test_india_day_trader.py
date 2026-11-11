from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from india_day_trader.risk import plan_trade, position_size
from india_day_trader.scanner import build_orb_signal, completed_candles, in_market_window

IST = ZoneInfo("Asia/Kolkata")


def test_orb_long_signal_requires_close_cross_and_trend_filter():
    now = datetime(2026, 11, 10, 10, 0, tzinfo=IST)
    times = pd.date_range("2026-11-10 09:15", periods=9, freq="5min", tz="Asia/Kolkata")
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),
        (99.0, 99.8, 98.5, 99.2, 1000),
        (99.2, 99.9, 98.8, 99.4, 1000),
        (99.4, 99.8, 99.0, 99.5, 1000),
        (99.5, 99.9, 99.2, 99.6, 1000),
        (99.6, 99.9, 99.3, 99.7, 1000),
        (99.7, 100.0, 99.4, 99.8, 1000),
        (99.8, 100.1, 99.5, 99.9, 1000),
        (99.9, 101.0, 99.8, 100.8, 2000),
    ]
    candles = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    candles.insert(0, "datetime", times)
    instrument = {"symbol": "NSE:TEST-EQ", "name": "TEST", "segment": "index", "use_vwap": False, "use_volume": False}
    settings = {"opening_range_minutes": 15, "opening_range_bars": 3, "entry_start": "09:45",
                "last_entry": "14:45", "min_total_bars": 8, "ema_period": 3,
                "target_rr": 2.0, "max_stop_pct": 5.0}
    signal = build_orb_signal(candles, instrument, settings, now)
    assert signal is not None
    assert signal["side"] == "long"
    assert signal["entry"] == 100.8
    assert signal["stop"] == 99.8
    assert signal["target"] == 102.8


def test_plan_trade_short_levels():
    plan = plan_trade("short", 100, 102, 2)
    assert plan["target"] == 96
    assert plan["risk_points"] == 2


def test_position_size_respects_risk_and_exposure_caps():
    qty = position_size(100, 98, 100000, risk_pct=0.5, max_exposure_pct=20)
    assert qty == 200


def test_completed_candles_discards_open_bar():
    now = datetime(2026, 11, 10, 9, 27, tzinfo=IST)
    raw = [
        [int(datetime(2026, 11, 10, 3, 45, tzinfo=ZoneInfo("UTC")).timestamp()), 100, 101, 99, 100, 500],
        [int(datetime(2026, 11, 10, 3, 55, tzinfo=ZoneInfo("UTC")).timestamp()), 100, 102, 99, 101, 600],
    ]
    out = completed_candles(raw, now, 5)
    assert len(out) == 1


def test_market_window_is_weekday_only_and_time_bounded():
    assert in_market_window(datetime(2026, 11, 10, 10, 0, tzinfo=IST))
    assert in_market_window(datetime(2026, 11, 10, 15, 0, tzinfo=IST))
    assert in_market_window(datetime(2026, 11, 10, 15, 45, tzinfo=IST))
    assert not in_market_window(datetime(2026, 11, 10, 16, 1, tzinfo=IST))
    assert not in_market_window(datetime(2026, 11, 8, 10, 0, tzinfo=IST))
