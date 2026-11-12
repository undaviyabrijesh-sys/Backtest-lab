"""Daily Indian-equity setup detectors adapted from day-trader-skill.

Research-only candidate detection. This module is separate from the existing
intraday ORB/Discord alert path and never emits executable trade instructions.
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
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100)
    return result.mask((avg_loss == 0) & (avg_gain == 0), 50)


def _validated(candles: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED - set(candles.columns)
    if missing:
        raise ValueError(f"missing candle columns: {', '.join(sorted(missing))}")
    df = candles.copy()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (df["volume"].dropna() < 0).any():
        raise ValueError("volume cannot be negative")
    return df


def scan_daily_setups(candles: pd.DataFrame, symbol: str) -> list[dict]:
    """Return long-only daily research candidates for NSE/BSE cash equities.

    * breakout_20d: latest completed close exceeds all 20 preceding closes.
    * bull_flag: >10% 10-session impulse followed by a five-session close range
      no wider than 5% of its mean.
    * reclaim_ema20: previous close at/below EMA20, latest close above EMA20.
    * oversold: Wilder RSI(14) below 30.
    * oversold_bounce: previous RSI below 30 and latest close higher.

    The lookbacks count Indian trading sessions, not calendar days. No entry,
    stop, target, quantity, leverage, or option-premium estimate is produced.
    """
    df = _validated(candles)
    if len(df) < 35:
        return []
    close = df["close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    rsi = rsi_wilder(close, 14)
    last = len(df) - 1
    current, previous = float(close.iloc[last]), float(close.iloc[last - 1])
    setups: list[str] = []

    prior_20 = close.iloc[last - 20:last]
    if len(prior_20) == 20 and current > float(prior_20.max()):
        setups.append("breakout_20d")

    impulse = close.iloc[last - 14:last - 4]
    consolidation = close.iloc[last - 4:last + 1]
    if len(impulse) == 10 and len(consolidation) == 5:
        impulse_return = float(impulse.iloc[-1] / impulse.iloc[0] - 1)
        width = float((consolidation.max() - consolidation.min()) / consolidation.mean())
        if impulse_return > 0.10 and width <= 0.05:
            setups.append("bull_flag")

    if previous <= float(ema20.iloc[last - 1]) and current > float(ema20.iloc[last]):
        setups.append("reclaim_ema20")

    current_rsi, previous_rsi = rsi.iloc[last], rsi.iloc[last - 1]
    if pd.notna(current_rsi) and float(current_rsi) < 30:
        setups.append("oversold")
    if pd.notna(previous_rsi) and float(previous_rsi) < 30 and current > previous:
        setups.append("oversold_bounce")

    return [{
        "symbol": symbol.upper(),
        "setup": setup,
        "side": "LONG",
        "market": "INDIA_CASH_EQUITY",
        "timeframe": "1d",
        "as_of": str(df.iloc[last]["timestamp"]),
        "close": current,
        "rsi14": None if pd.isna(current_rsi) else round(float(current_rsi), 2),
        "ema20": round(float(ema20.iloc[last]), 4),
        "status": "RESEARCH_CANDIDATE",
        "source": "day-trader-skill daily setup adaptation",
    } for setup in setups]
