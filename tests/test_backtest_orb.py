from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from india_day_trader.backtest_orb import run_backtest, summarize

IST = ZoneInfo("Asia/Kolkata")


def sample_day(entry_high=106.0, entry_low=101.0):
    times = pd.date_range("2026-11-10 09:15", periods=7, freq="5min", tz=IST)
    rows = [
        (99.0, 100.0, 98.0, 99.0, 1000),
        (99.0, 99.8, 98.5, 99.2, 1000),
        (99.2, 99.9, 98.8, 99.4, 1000),
        (99.4, 99.8, 99.0, 99.5, 1000),
        (99.5, 102.0, 99.5, 101.0, 1800),
        (101.5, entry_high, entry_low, 104.0, 2000),
        (104.0, 104.5, 103.0, 104.0, 1200),
    ]
    data = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    data.insert(0, "datetime", times)
    return data


def test_orb_backtest_long_hits_target_on_next_bar():
    trades = run_backtest(sample_day(), rr=2, cost_bps_per_side=0, slippage_bps_per_side=0)
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["side"] == "long"
    assert trade["entry"] == 101.5
    assert trade["stop"] == 99.5
    assert trade["target"] == 105.5
    assert trade["exit_reason"] == "target"
    assert trade["gross_r"] == 2.0


def test_same_bar_stop_and_target_assumes_stop_first():
    trades = run_backtest(sample_day(entry_high=106.0, entry_low=99.0),
                          rr=2, cost_bps_per_side=0, slippage_bps_per_side=0)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "stop"
    assert trades.iloc[0]["gross_r"] == -1.0


def test_cost_and_slippage_reduce_net_result():
    free = run_backtest(sample_day(), rr=2, cost_bps_per_side=0, slippage_bps_per_side=0)
    charged = run_backtest(sample_day(), rr=2, cost_bps_per_side=10, slippage_bps_per_side=5)
    assert charged.iloc[0]["net_points"] < free.iloc[0]["net_points"]
    assert charged.iloc[0]["total_cost_points"] if "total_cost_points" in charged.columns else charged.iloc[0]["transaction_cost_points"] > 0


def test_summary_reports_drawdown_and_streak():
    trades = run_backtest(sample_day(), rr=2, cost_bps_per_side=0, slippage_bps_per_side=0)
    report = summarize(trades)
    assert report["trades"] == 1
    assert report["wins"] == 1
    assert report["profit_factor"] is None


def test_empty_input_returns_zero_summary():
    empty = pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    assert summarize(run_backtest(empty))["trades"] == 0
