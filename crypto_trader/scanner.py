"""Research-only scanner for skill-inspired crypto daily setups.

Run: python -m crypto_trader.scanner [--limit 10]
No Discord delivery or order execution is wired in at this stage.
"""
import argparse
import json

from .binance_source import fetch_daily_klines, top_usdt_perpetuals
from .skill_setups import scan_daily_setups


def run(limit: int = 10) -> list[dict]:
    markets = top_usdt_perpetuals(limit)
    results = []
    failures = []
    for market in markets:
        symbol = market["symbol"]
        try:
            candles = fetch_daily_klines(symbol, 100)
            for candidate in scan_daily_setups(candles, symbol):
                candidate["quote_volume_24h"] = market["quote_volume_24h"]
                candidate["last_price"] = market["last_price"]
                results.append(candidate)
        except Exception as exc:
            failures.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps({
        "market": "Binance USD-M perpetuals",
        "universe_count": len(markets),
        "scanned_symbols": [m["symbol"] for m in markets],
        "candidate_count": len(results),
        "candidates": results,
        "failures": failures,
        "disclaimer": "Research candidates only; no entry/SL/TP or order is generated. Backtest before alert promotion.",
    }, indent=2, default=str))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    run(args.limit)


if __name__ == "__main__":
    main()
