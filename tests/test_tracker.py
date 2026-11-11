from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from india_day_trader.tracker import advance_signal

IST = ZoneInfo("Asia/Kolkata")


def signal(side="long"):
    return {
        "symbol": "NSE:TEST-EQ", "name": "TEST", "side": side,
        "entry": 100.0, "stop": 99.0 if side == "long" else 101.0,
        "target": 102.0 if side == "long" else 98.0,
        "status": "OPEN",
        "last_checked_timestamp": datetime(2026, 11, 10, 9, 35, tzinfo=IST).isoformat(),
    }


def bars(rows):
    frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    return frame


def test_tracker_closes_long_at_target_after_signal_bar():
    data = bars([
        ["2026-11-10 09:35:00+05:30", 100, 102, 99.5, 101, 1000],
        ["2026-11-10 09:40:00+05:30", 101, 103, 100.5, 102, 1200],
    ])
    updated, event = advance_signal(signal(), data, datetime(2026, 11, 10, 9, 50, tzinfo=IST))
    assert event == "TARGET_HIT"
    assert updated["status"] == "CLOSED"
    assert updated["exit_price"] == 102
    assert updated["r_multiple"] == 2


def test_tracker_assumes_stop_first_when_both_hit():
    data = bars([
        ["2026-11-10 09:40:00+05:30", 100, 103, 98, 101, 1200],
    ])
    updated, event = advance_signal(signal(), data, datetime(2026, 11, 10, 9, 50, tzinfo=IST))
    assert event == "STOP_LOSS_HIT"
    assert updated["pnl_points"] == -1


def test_tracker_handles_short_target():
    data = bars([
        ["2026-11-10 09:40:00+05:30", 100, 100.5, 97.5, 98, 1000],
    ])
    updated, event = advance_signal(signal("short"), data, datetime(2026, 11, 10, 9, 50, tzinfo=IST))
    assert event == "TARGET_HIT"
    assert updated["r_multiple"] == 2


def test_tracker_ignores_signal_candle_and_duplicate_bars():
    data = bars([
        ["2026-11-10 09:35:00+05:30", 100, 103, 98, 101, 1000],
    ])
    updated, event = advance_signal(signal(), data, datetime(2026, 11, 10, 9, 50, tzinfo=IST))
    assert event is None
    assert updated["status"] == "OPEN"


def test_tracker_flattens_at_session_cutoff():
    data = bars([
        ["2026-11-10 15:15:00+05:30", 100, 101, 99.5, 100.5, 1000],
    ])
    base = signal()
    base["last_checked_timestamp"] = datetime(2026, 11, 10, 15, 10, tzinfo=IST).isoformat()
    updated, event = advance_signal(base, data, datetime(2026, 11, 10, 15, 20, tzinfo=IST))
    assert event == "EOD_EXIT"
    assert updated["exit_price"] == 100.5
