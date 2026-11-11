from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from india_day_trader.research_matrix import chronological_split, default_variants, run_matrix

IST = ZoneInfo("Asia/Kolkata")


def multi_session_candles():
    frames = []
    start = date(2026, 10, 1)
    for day_offset in range(10):
        day = start + timedelta(days=day_offset)
        times = pd.date_range(f"{day.isoformat()} 09:15", periods=7, freq="5min", tz=IST)
        rows = [
            (99.0, 100.0, 98.0, 99.0, 1000),
            (99.0, 99.8, 98.5, 99.2, 1000),
            (99.2, 99.9, 98.8, 99.4, 1000),
            (99.4, 99.8, 99.0, 99.5, 1000),
            (99.5, 102.0, 99.5, 101.0, 1800),
            (101.5, 106.0, 101.0, 104.0, 2000),
            (104.0, 104.5, 103.0, 104.0, 1200),
        ]
        frame = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
        frame.insert(0, "datetime", times)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_chronological_split_has_no_overlapping_sessions():
    train, test = chronological_split(multi_session_candles(), 0.7)
    train_days = set(train["datetime"].dt.date)
    test_days = set(test["datetime"].dt.date)
    assert len(train_days) == 7
    assert len(test_days) == 3
    assert max(train_days) < min(test_days)


def test_default_grid_is_explicit_and_bounded():
    variants = default_variants()
    assert len(variants) == 36
    assert {v["rr"] for v in variants} == {1.0, 1.5, 2.0, 3.0}


def test_matrix_reports_in_sample_and_later_out_of_sample():
    variants = [
        {"name": "test_rr2", "rr": 2, "ema_period": 3},
        {"name": "test_rr1", "rr": 1, "ema_period": 3},
    ]
    matrix = run_matrix(
        multi_session_candles(), cost_bps_per_side=0, slippage_bps_per_side=0,
        train_fraction=0.7, variants=variants, min_oos_trades=2
    )
    assert len(matrix) == 2
    assert "out_sample_expectancy_net_r" in matrix.columns
    assert matrix["out_sample_trades"].max() == 3


def test_split_requires_multiple_sessions():
    one_day = multi_session_candles().iloc[:7]
    with pytest.raises(ValueError):
        chronological_split(one_day)
