import pandas as pd
import pytest
from crypto_trader.skill_setups import rsi_wilder,scan_intraday_setups

def frame(closes):
    return pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=len(closes),freq="15min",tz="UTC"),
      "open":closes,"high":[x*1.002 for x in closes],"low":[x*.998 for x in closes],
      "close":closes,"volume":[1000.0]*len(closes)})

def test_requires_35_bars():
    assert scan_intraday_setups(frame([100+i for i in range(34)]),"BTCUSDT")==[]

def test_20_bar_breakout():
    hits=scan_intraday_setups(frame([100+(i%4) for i in range(79)]+[120]),"BTCUSDT")
    assert "breakout_20bar" in {x["setup"] for x in hits}
    assert all(x["timeframe"]=="15m" for x in hits)

def test_bull_flag():
    c=[100.0]*70+[100,100.4,100.8,101.2,101.6,102,102.4,102.8,103.2,103.6]+[103.2,103.5,103.3,103.6,103.4]
    assert "bull_flag" in {x["setup"] for x in scan_intraday_setups(frame(c),"ETHUSDT")}

def test_latest_bar_in_flag_range():
    c=[100.0]*70+[100,100.4,100.8,101.2,101.6,102,102.4,102.8,103.2,103.6]+[103.2,103.5,103.3,103.6,108]
    assert "bull_flag" not in {x["setup"] for x in scan_intraday_setups(frame(c),"BTCUSDT")}

def test_rsi_bounds():
    assert rsi_wilder(pd.Series([100+i for i in range(30)])).dropna().between(0,100).all()

def test_invalid_price_rejected():
    data=frame([100+i for i in range(40)]); data.loc[0,"close"]=-1
    with pytest.raises(ValueError): scan_intraday_setups(data,"BTCUSDT")
