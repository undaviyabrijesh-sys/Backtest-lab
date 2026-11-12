"""Daily long-setup detectors adapted from Jakeschincariol/day-trader-skill.

These functions identify research candidates, not executable or validated trades.
The source skill's US-equity session ORB is intentionally not copied into 24/7
crypto markets. Its daily close-based setup concepts are retained.
"""
from __future__ import annotations

import pandas as pd


REQUIRED = {"timestamp", "open", "high", "low", "close", "volume"}


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return rsi


def _validated(candles: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED - set(candles.columns)
    if missing:
        raise ValueError(f"missing candle columns: {', '.join(sorted(missing))}")
    df = candles.copy()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    return df


def scan_daily_setups(candles: pd.DataFrame, symbol: str) -> list[dict]:
    """Return skill-inspired long candidates from completed daily OHLCV bars.

    Rules mirror the source skill's close-based daily scanner:
    * breakout_20d: latest close above all 20 preceding closes.
    * bull_flag: >10% impulse across the 10 bars before a 5-bar consolidation;
      the five consolidation closes must fit inside a 5% range.
    * reclaim_ema20: previous close <= its EMA20, latest close > its EMA20.
    * oversold: Wilder RSI(14) < 30.
    * oversold_bounce: prior RSI(14) < 30 and latest close is higher.

    No entry, stop, target, leverage, or position size is inferred here.
    """
    df = _validated(candles)
    if len(df) < 35:
        return []
    close = df["close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    rsi = rsi_wilder(close, 14)
    last = len(df) - 1
    c = float(close.iloc[last])
    prev = float(close.iloc[last - 1])
    setups: list[str] = []

    prior_20 = close.iloc[last - 20:last]
    if len(prior_20) == 20 and c > float(prior_20.max()):
        setups.append("breakout_20d")

    impulse = close.iloc[last - 15:last - 5]
    consolidation = close.iloc[last - 5:last]
    if len(impulse) == 10 and len(consolidation) == 5:
        impulse_return = float(impulse.iloc[-1] / impulse.iloc[0] - 1)
        consolidation_range = float(
            (consolidation.max() - consolidation.min()) / consolidation.mean()
        )
        if impulse_return > 0.10 and consolidation_range <= 0.05:
            setups.append("bull_flag")

    if prev <= float(ema20.iloc[last - 1]) and c > float(ema20.iloc[last]):
        setups.append("reclaim_ema20")

    latest_rsi = rsi.iloc[last]
    previous_rsi = rsi.iloc[last - 1]
    if pd.notna(latest_rsi) and float(latest_rsi) < 30:
        setups.append("oversold")
    if pd.notna(previous_rsi) and float(previous_rsi) < 30 and c > prev:
        setups.append("oversold_bounce")

    return [{
        "symbol": symbol.upper(),
        "setup": setup,
        "side": "LONG",
        "timeframe": "1d",
        "as_of": str(df.iloc[last]["timestamp"]),
        "close": c,
        "rsi14": None if pd.isna(latest_rsi) else round(float(latest_rsi), 2),
        "ema20": round(float(ema20.iloc[last]), 8),
        "status": "RESEARCH_CANDIDATE",
        "source": "day-trader-skill daily setup adaptation",
    } for setup in setups]
