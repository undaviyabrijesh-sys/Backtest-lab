"""Read-only public Binance USD-M perpetual market data."""
from __future__ import annotations
import json
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import pandas as pd
BASE="https://fapi.binance.com"
EXCLUDED_BASES={"USDC","BUSD","FDUSD","TUSD","USDP","DAI","USDE","USTC"}

def _get_json(path,params=None,timeout=15):
    url=BASE+path
    if params: url+="?"+urlencode(params)
    req=Request(url,headers={"User-Agent":"Backtest-lab-crypto-research/1.0"})
    with urlopen(req,timeout=timeout) as response:
        if response.status!=200: raise RuntimeError(f"Binance returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def top_usdt_perpetuals(limit=10):
    if not 1<=int(limit)<=50: raise ValueError("limit must be between 1 and 50")
    info=_get_json("/fapi/v1/exchangeInfo")
    allowed={x["symbol"]:x for x in info.get("symbols",[]) if x.get("status")=="TRADING" and x.get("contractType")=="PERPETUAL" and x.get("quoteAsset")=="USDT" and x.get("baseAsset") not in EXCLUDED_BASES}
    ranked=[]
    for t in _get_json("/fapi/v1/ticker/24hr"):
        symbol=t.get("symbol")
        if symbol not in allowed: continue
        try: volume=float(t.get("quoteVolume",0)); price=float(t.get("lastPrice",0))
        except (TypeError,ValueError): continue
        if volume>0 and price>0:
            ranked.append({"symbol":symbol,"base_asset":allowed[symbol]["baseAsset"],"quote_asset":"USDT","quote_volume_24h":volume,"last_price":price})
    return sorted(ranked,key=lambda x:x["quote_volume_24h"],reverse=True)[:limit]

def fetch_intraday_klines(symbol,interval="15m",limit=200):
    """Fetch intraday candles and drop any still-forming bar."""
    if interval not in {"5m","15m","30m","1h"}: raise ValueError("unsupported intraday interval")
    if not 35<=int(limit)<=1000: raise ValueError("limit must be between 35 and 1000")
    rows=_get_json("/fapi/v1/klines",{"symbol":symbol.upper(),"interval":interval,"limit":limit})
    cols=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"]
    df=pd.DataFrame(rows,columns=cols)
    if df.empty: return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
    df["timestamp"]=pd.to_datetime(df["open_time"],unit="ms",utc=True)
    for c in ("open","high","low","close","volume"): df[c]=pd.to_numeric(df[c],errors="coerce")
    now_ms=pd.Timestamp.now(tz="UTC").timestamp()*1000
    df=df[df["close_time"].astype("int64")<now_ms]
    return df[["timestamp","open","high","low","close","volume"]].reset_index(drop=True)
