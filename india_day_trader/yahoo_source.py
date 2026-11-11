"""Yahoo Finance market-data adapter for Indian cash equities and indices.

This is an unofficial, best-effort source. Yahoo intraday candles may be delayed,
missing or revised; never treat these as broker-grade execution data.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")

INDEX_TICKERS = {
    "NSE:NIFTY50-INDEX": "^NSEI",
    "NSE:NIFTYBANK-INDEX": "^NSEBANK",
    "BSE:SENSEX-INDEX": "^BSESN",
}


def yahoo_ticker(symbol):
    """Translate the repository's FYERS-style watchlist symbol to Yahoo format."""
    if symbol in INDEX_TICKERS:
        return INDEX_TICKERS[symbol]
    if symbol.startswith("NSE:") and symbol.endswith("-EQ"):
        return symbol[4:-3] + ".NS"
    if symbol.startswith("BSE:") and symbol.endswith("-EQ"):
        return symbol[4:-3] + ".BO"
    raise ValueError(f"No Yahoo Finance ticker mapping for {symbol!r}")


def normalize_yahoo_frame(frame, now=None, interval_minutes=5):
    """Normalize Yahoo OHLCV to IST and retain only completed bars from today."""
    columns = ["datetime", "open", "high", "low", "close", "volume"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    df = frame.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(column).lower().replace(" ", "_") for column in df.columns]
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Yahoo response missing columns: {missing}")
    index = pd.DatetimeIndex(df.index)
    if index.tz is None:
        index = index.tz_localize(IST)
    else:
        index = index.tz_convert(IST)
    df["datetime"] = index
    for column in required:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    now = (now or datetime.now(IST)).astimezone(IST)
    df = df[(df["datetime"].dt.date == now.date()) &
            ((df["datetime"] + pd.Timedelta(minutes=interval_minutes)) <= now)]
    return df[columns].sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)


def fetch_yahoo_candles(instrument, now=None):
    """Download the current session's 5-minute bars for one watchlist instrument."""
    import yfinance as yf

    now = (now or datetime.now(IST)).astimezone(IST)
    ticker = yahoo_ticker(instrument["symbol"])
    history = yf.Ticker(ticker).history(
        period="1d",
        interval="5m",
        auto_adjust=False,
        actions=False,
        prepost=False,
        timeout=20,
    )
    bars = normalize_yahoo_frame(history, now=now, interval_minutes=5)
    if bars.empty:
        raise RuntimeError(f"Yahoo Finance returned no completed 5-minute candles for {ticker}")
    return bars
