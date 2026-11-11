from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from india_day_trader.pdh_pdl_sweep import run_backtest

IST = ZoneInfo("Asia/Kolkata")


def sweep_fixture():
    frames = []
    day1 = date(2026, 11, 9)
    t1 = pd.date_range(f"{day1.isoformat()} 09:15", periods=3, freq="5min", tz=IST)
    r1 = [
        (100, 110, 90, 100, 1000),
        (100, 108, 92, 101, 1000),
        (101, 107, 94, 100, 1000),
    ]
    f1 = pd.DataFrame(r1, columns=["open", "high", "low", "close", "volume"])
    f1.insert(0, "datetime", t1)
    frames.append(f1)

    day2 = date(2026, 11, 10)
    t2 = pd.date_range(f"{day2.isoformat()} 09:15", periods=6, freq="5min", tz=IST)
    r2 = [
        (100, 102, 98, 100, 1000),
        (100, 101.5, 98.5, 100, 1000),
        (100, 101.8, 98.2, 100, 1000),
        (109, 111, 108.8, 109, 1600),       # sweeps PDH=110, closes back below
        (108.5, 109, 108.4, 108.7, 1800),   # breaks sweep candle low; short entry
        (108, 108.2, 103.0, 104, 2000),     # reaches 2R target
    ]
    f2 = pd.DataFrame(r2, columns=["open", "high", "low", "close", "volume"])
    f2.insert(0, "datetime", t2)
    frames.append(f2)
    return pd.concat(frames, ignore_index=True)


def test_pdh_sweep_reversal_triggers_short_and_reaches_target():
    trades = run_backtest(sweep_fixture(), rr=2, max_stop_pct=5,
                          cost_bps_per_side=0, slippage_bps_per_side=0)
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["strategy"] == "pdh_pdl_sweep_reversal_v1"
    assert trade["swept_level"] == "PDH"
    assert trade["side"] == "short"
    assert trade["exit_reason"] == "target"
    assert trade["gross_r"] == 2


def test_single_session_cannot_use_its_own_future_high_low():
    candles = sweep_fixture().iloc[-6:].copy()
    trades = run_backtest(candles, max_stop_pct=5, cost_bps_per_side=0, slippage_bps_per_side=0)
    assert trades.empty


def test_same_bar_stop_and_target_is_conservative():
    data = sweep_fixture().copy()
    data.loc[data.index[-1], "high"] = 112
    # Target touched as well as the pre-existing short stop on the same bar.
    trades = run_backtest(data, rr=2, max_stop_pct=5,
                          cost_bps_per_side=0, slippage_bps_per_side=0)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "stop"
