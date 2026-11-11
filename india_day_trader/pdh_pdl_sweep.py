"""Prior-day high/low liquidity-sweep reversal backtester (experimental).

A completed 5-minute candle must sweep a prior-session extreme and close back
inside that level. The next candle must break the sweep candle's opposite edge.
Entries are simulated only after that confirmation; no live order code exists.
"""
from datetime import time

import pandas as pd

from .backtest_orb import _exit_trade, normalize_candles


def run_backtest(candles, rr=2.0, cost_bps_per_side=10.0,
                 slippage_bps_per_side=2.0, max_stop_pct=2.0,
                 max_trades_per_session=1, entry_start="09:30",
                 last_entry="14:45"):
    if rr <= 0 or cost_bps_per_side < 0 or slippage_bps_per_side < 0:
        raise ValueError("RR must be positive and cost/slippage cannot be negative")
    if max_trades_per_session < 1:
        raise ValueError("max_trades_per_session must be at least 1")

    df = normalize_candles(candles)
    if df.empty:
        return pd.DataFrame()
    df["session"] = df["datetime"].dt.date
    daily = df.groupby("session").agg(
        previous_high=("high", "max"),
        previous_low=("low", "min"),
    )
    daily["pdh"] = daily["previous_high"].shift(1)
    daily["pdl"] = daily["previous_low"].shift(1)
    trades = []

    for session, original_day in df.groupby("session", sort=True):
        if session not in daily.index:
            continue
        pdh = daily.loc[session, "pdh"]
        pdl = daily.loc[session, "pdl"]
        if pd.isna(pdh) or pd.isna(pdl):
            continue
        pdh, pdl = float(pdh), float(pdl)
        day = original_day.reset_index(drop=True)
        times = day["datetime"].dt.time
        start = time.fromisoformat(entry_start)
        end = time.fromisoformat(last_entry)
        eligible = [i for i, tm in enumerate(times) if start <= tm <= end]
        trades_today = 0

        for idx in eligible:
            if idx >= len(day) - 1 or trades_today >= max_trades_per_session:
                break
            sweep = day.iloc[idx]
            prev_high = float(sweep["high"])
            prev_low = float(sweep["low"])
            close = float(sweep["close"])

            swept_high = prev_high > pdh and close < pdh
            swept_low = prev_low < pdl and close > pdl
            # A candle that sweeps both sides is ambiguous; ignore it.
            if swept_high == swept_low:
                continue

            if swept_high:
                side = "short"
                trigger = prev_low
                stop = prev_high
                touched = float(day.iloc[idx + 1]["low"]) < trigger
            else:
                side = "long"
                trigger = prev_high
                stop = prev_low
                touched = float(day.iloc[idx + 1]["high"]) > trigger
            if not touched:
                continue

            next_bar = day.iloc[idx + 1]
            raw_open = float(next_bar["open"])
            entry = min(raw_open, trigger) if side == "short" else max(raw_open, trigger)
            risk = stop - entry if side == "short" else entry - stop
            if risk <= 0 or entry <= 0 or risk / entry * 100.0 > max_stop_pct:
                continue
            target = entry - rr * risk if side == "short" else entry + rr * risk

            trade = _exit_trade(
                session, day, idx + 1, side, entry, stop, target,
                cost_bps_per_side, slippage_bps_per_side, sweep["datetime"]
            )
            if trade:
                trade.update({
                    "strategy": "pdh_pdl_sweep_reversal_v1",
                    "swept_level": "PDH" if swept_high else "PDL",
                    "previous_day_high": pdh,
                    "previous_day_low": pdl,
                    "sweep_high": prev_high,
                    "sweep_low": prev_low,
                    "trigger": trigger,
                })
                trades.append(trade)
                trades_today += 1
                # One trade per session is the default; don't overlap positions.
                break

    return pd.DataFrame(trades)
