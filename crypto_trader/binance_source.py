"""Public Binance USD-M perpetual market data; read-only, no API key required."""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

BASE = "https://fapi.binance.com"
EXCLUDED_BASES = {"USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI", "USDE", "USTC"}


def _get_json(path: str, params: dict | None = None, timeout: int = 15):
    url = BASE + path
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "Backtest-lab-crypto-research/1.0"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Binance returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def top_usdt_perpetuals(limit: int = 10) -> list[dict]:
    """Return top active USDT-margined perpetual contracts by 24h quote volume."""
    if not 1 <= int(limit) <= 50:
        raise ValueError("limit must be between 1 and 50")
    info = _get_json("/fapi/v1/exchangeInfo")
    allowed = {
        item["symbol"]: item for item in info.get("symbols", [])
        if item.get("status") == "TRADING"
        and item.get("contractType") == "PERPETUAL"
        and item.get("quoteAsset") == "USDT"
        and item.get("baseAsset") not in EXCLUDED_BASES
    }
    tickers = _get_json("/fapi/v1/ticker/24hr")
    ranked = []
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if symbol not in allowed:
            continue
        try:
            volume = float(ticker.get("quoteVolume", 0))
            price = float(ticker.get("lastPrice", 0))
        except (TypeError, ValueError):
            continue
        if volume <= 0 or price <= 0:
            continue
        meta = allowed[symbol]
        ranked.append({
            "symbol": symbol,
            "base_asset": meta["baseAsset"],
            "quote_asset": "USDT",
            "quote_volume_24h": volume,
            "last_price": price,
        })
    return sorted(ranked, key=lambda x: x["quote_volume_24h"], reverse=True)[:limit]


def fetch_daily_klines(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch daily futures candles and remove the still-forming UTC candle."""
    if not 35 <= int(limit) <= 500:
        raise ValueError("limit must be between 35 and 500")
    rows = _get_json("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": "1d", "limit": limit})
    columns = ["open_time", "open", "high", "low", "close", "volume",
               "close_time", "quote_volume", "trades", "taker_buy_base",
               "taker_buy_quote", "ignore"]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    now_ms = pd.Timestamp.now(tz="UTC").timestamp() * 1000
    df = df[df["close_time"].astype("int64") < now_ms]
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
