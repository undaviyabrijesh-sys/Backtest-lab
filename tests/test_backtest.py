import pandas as pd
from backtest import run_backtest, summary

def test_empty():
    assert summary(run_backtest(pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])))["trades"] == 0

def test_no_future_day_levels():
    data = pd.DataFrame([
        ["2026-01-01 09:15:00+05:30",100,110,90,100,1],
        ["2026-01-02 09:15:00+05:30",100,105,95,100,1],
        ["2026-01-02 09:30:00+05:30",100,112,99,111,1],
        ["2026-01-02 09:45:00+05:30",111,114,108,113,1],
    ], columns=["datetime","open","high","low","close","volume"])
    trades = run_backtest(data)
    assert len(trades) == 1
    assert trades.iloc[0]["side"] == "long"
    assert trades.iloc[0]["entry"] == 112
