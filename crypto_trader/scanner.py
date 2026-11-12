"""Research-only scanner for intraday crypto skill-inspired setups."""
import argparse,json
from .binance_source import fetch_intraday_klines,top_usdt_perpetuals
from .skill_setups import scan_intraday_setups

def run(limit=10,interval="15m"):
    markets=top_usdt_perpetuals(limit); results=[]; failures=[]
    for market in markets:
        symbol=market["symbol"]
        try:
            bars=fetch_intraday_klines(symbol,interval=interval,limit=200)
            for candidate in scan_intraday_setups(bars,symbol,timeframe=interval):
                candidate["quote_volume_24h"]=market["quote_volume_24h"]
                candidate["last_price"]=market["last_price"]; results.append(candidate)
        except Exception as exc: failures.append({"symbol":symbol,"error":f"{type(exc).__name__}: {exc}"})
    print(json.dumps({"market":"Binance USD-M perpetuals","timeframe":interval,"universe_count":len(markets),
      "scanned_symbols":[m["symbol"] for m in markets],"candidate_count":len(results),"candidates":results,
      "failures":failures,"disclaimer":"Intraday research candidates only; no entry/SL/TP or order is generated."},indent=2,default=str))
    return results

def main():
    p=argparse.ArgumentParser(); p.add_argument("--limit",type=int,default=10)
    p.add_argument("--interval",choices=["5m","15m","30m","1h"],default="15m")
    a=p.parse_args(); run(a.limit,a.interval)
if __name__=="__main__": main()
