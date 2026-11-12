"""Intraday long-setup detectors adapted from day-trader-skill."""
from __future__ import annotations
import pandas as pd
REQUIRED = {"timestamp", "open", "high", "low", "close", "volume"}

def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta=close.astype(float).diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    ag=gain.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    al=loss.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    rs=ag/al.replace(0,float("nan")); out=100-(100/(1+rs))
    out=out.mask((al==0)&(ag>0),100)
    return out.mask((al==0)&(ag==0),50)

def _validated(candles):
    missing=REQUIRED-set(candles.columns)
    if missing: raise ValueError(f"missing candle columns: {', '.join(sorted(missing))}")
    df=candles.copy()
    for c in ("open","high","low","close","volume"): df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=["open","high","low","close"]).sort_values("timestamp").drop_duplicates("timestamp",keep="last").reset_index(drop=True)
    if (df[["open","high","low","close"]]<=0).any().any(): raise ValueError("OHLC prices must be positive")
    if (df["volume"].dropna()<0).any(): raise ValueError("volume cannot be negative")
    return df

def scan_intraday_setups(candles, symbol, timeframe="15m", impulse_min_pct=0.02, flag_max_range_pct=0.015):
    """Completed-bar scan: 20-bar breakout, 10-bar impulse plus 5-bar flag,
    EMA20 reclaim, RSI14 oversold and oversold bounce. Thresholds are research defaults."""
    if impulse_min_pct<=0 or flag_max_range_pct<=0: raise ValueError("flag thresholds must be positive")
    df=_validated(candles)
    if len(df)<35: return []
    close=df["close"].astype(float); ema=close.ewm(span=20,adjust=False).mean(); rsi=rsi_wilder(close,14)
    last=len(df)-1; cur=float(close.iloc[last]); prev=float(close.iloc[last-1]); setups=[]
    if cur>float(close.iloc[last-20:last].max()): setups.append("breakout_20bar")
    impulse=close.iloc[last-14:last-4]; flag=close.iloc[last-4:last+1]
    if len(impulse)==10 and len(flag)==5:
        ret=float(impulse.iloc[-1]/impulse.iloc[0]-1); width=float((flag.max()-flag.min())/flag.mean())
        if ret>=impulse_min_pct and width<=flag_max_range_pct: setups.append("bull_flag")
    if prev<=float(ema.iloc[last-1]) and cur>float(ema.iloc[last]): setups.append("reclaim_ema20")
    cr,pr=rsi.iloc[last],rsi.iloc[last-1]
    if pd.notna(cr) and float(cr)<30: setups.append("oversold")
    if pd.notna(pr) and float(pr)<30 and cur>prev: setups.append("oversold_bounce")
    return [{"symbol":symbol.upper(),"setup":s,"side":"LONG","timeframe":timeframe,
      "as_of":str(df.iloc[last]["timestamp"]),"close":cur,
      "rsi14":None if pd.isna(cr) else round(float(cr),2),"ema20":round(float(ema.iloc[last]),8),
      "status":"RESEARCH_CANDIDATE","source":"day-trader-skill intraday setup adaptation"} for s in setups]
