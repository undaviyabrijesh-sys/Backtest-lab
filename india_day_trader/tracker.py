"""Paper signal outcome tracker. This observes OHLC outcomes; it does not verify broker fills."""
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")


def advance_signal(signal, candles, now=None, flat_time="15:20"):
    """Advance a reference signal through unprocessed completed candles.

    Returns (updated_signal, event). Stop is assumed first if stop and target
    are both touched in a single candle. Entry is a reference price, not a fill.
    """
    updated = dict(signal)
    if updated.get("status", "OPEN") != "OPEN":
        return updated, None
    if candles is None or candles.empty:
        return updated, None

    last_checked = pd.Timestamp(updated["last_checked_timestamp"])
    if last_checked.tzinfo is None:
        last_checked = last_checked.tz_localize(IST)
    else:
        last_checked = last_checked.tz_convert(IST)

    df = candles.copy().sort_values("datetime").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize(IST)
    else:
        df["datetime"] = df["datetime"].dt.tz_convert(IST)
    df = df[df["datetime"] > last_checked]
    now = (now or pd.Timestamp.now(tz=IST).to_pydatetime()).astimezone(IST)
    force_flat = time.fromisoformat(flat_time)

    for _, bar in df.iterrows():
        side = updated["side"]
        stop = float(updated["stop"])
        target = float(updated["target"])
        entry = float(updated["entry"])
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if side == "long":
            stop_hit = low <= stop
            target_hit = high >= target
        else:
            stop_hit = high >= stop
            target_hit = low <= target

        event = None
        if stop_hit:
            exit_price = min(stop, open_price) if side == "long" else max(stop, open_price)
            event = "STOP_LOSS_HIT"
        elif target_hit:
            exit_price = target
            event = "TARGET_HIT"
        elif now.time() >= force_flat and (bar["datetime"] + pd.Timedelta(minutes=5)).time() >= force_flat:
            exit_price = close
            event = "EOD_EXIT"

        updated["last_checked_timestamp"] = bar["datetime"].isoformat()
        updated["last_checked_close"] = close
        if event:
            direction = 1.0 if side == "long" else -1.0
            risk = abs(entry - stop)
            pnl = (exit_price - entry) * direction
            updated.update({
                "status": "CLOSED",
                "outcome": event,
                "exit_time": bar["datetime"].isoformat(),
                "exit_price": float(exit_price),
                "pnl_points": float(pnl),
                "r_multiple": float(pnl / risk) if risk else None,
            })
            return updated, event

    return updated, None
