import pandas as pd
import pytest
from india_day_trader.skill_setups import rsi_wilder,scan_intraday_setups

def frame(closes):
    return pd.DataFrame({"timestamp":pd.date_range("2026-11-12 09:15",periods=len(closes),freq="5min"),
      "open":closes,"high":[x*1.001 for x in closes],"low":[x*.999 for x in closes],
      "close":closes,"volume":[100000.0]*len(closes)})

def names(hits): return {x["setup"] for x in hits}

def test_minimum_bars():
    assert scan_intraday_setups(frame([100+i for i in range(34)]),"RELIANCE.NS")==[]

def test_breakout_and_equity():
    hits=scan_intraday_setups(frame([100+(i%4) for i in range(79)]+[120]),"RELIANCE.NS")
    assert "breakout_20bar" in names(hits)
    assert all(x["market"]=="INDIA_CASH_EQUITY" and x["timeframe"]=="5m" for x in hits)

def test_bull_flag():
    c=[100.0]*70+[100,100.2,100.4,100.6,100.8,101,101.2,101.4,101.6,101.8]+[101.6,101.7,101.65,101.75,101.7]
    assert "bull_flag" in names(scan_intraday_setups(frame(c),"TCS.NS"))

def test_index_classification():
    c=[100+(i%4) for i in range(79)]+[120]
    assert all(x["market"]=="INDIA_INDEX" for x in scan_intraday_setups(frame(c),"NSE:NIFTY50-INDEX"))
    assert all(x["market"]=="INDIA_INDEX" for x in scan_intraday_setups(frame(c),"BANKNIFTY",market="INDIA_INDEX"))

def test_latest_bar_in_flag_range():
    c=[100.0]*70+[100,100.2,100.4,100.6,100.8,101,101.2,101.4,101.6,101.8]+[101.6,101.7,101.65,101.75,110]
    assert "bull_flag" not in names(scan_intraday_setups(frame(c),"INFY.NS"))

def test_does_not_mix_sessions():
    a=frame([100+(i%4) for i in range(40)])
    b=frame([100+(i%4) for i in range(20)]); b["timestamp"]+=pd.Timedelta(days=1)
    assert scan_intraday_setups(pd.concat([a,b]),"NIFTY")==[]

def test_rsi_and_invalid_market():
    assert rsi_wilder(pd.Series([100+i for i in range(30)])).dropna().between(0,100).all()
    with pytest.raises(ValueError): scan_intraday_setups(frame([100+i for i in range(40)]),"NIFTY",market="OPTIONS")

def test_invalid_prices_and_volume():
    d=frame([100+i for i in range(40)]); d.loc[0,"close"]=-1
    with pytest.raises(ValueError): scan_intraday_setups(d,"SBIN.NS")
    d=frame([100+i for i in range(40)]); d.loc[0,"volume"]=-1
    with pytest.raises(ValueError): scan_intraday_setups(d,"SBIN.NS")
